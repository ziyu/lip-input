package dev.lipinput

import android.Manifest
import android.app.AlertDialog
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.InputMethodManager
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FallbackStrategy
import androidx.camera.video.FileOutputOptions
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import okhttp3.Call
import java.io.File
import java.util.Locale

class MainActivity : ComponentActivity() {
    private val flow = CaptureFlow()
    private val requestGate = RequestGate()
    private val handler = Handler(Looper.getMainLooper())
    private val api = LipApi()
    private var call: Call? = null
    private var capabilities: Capabilities? = null
    private var verifiedEndpoint: Endpoint? = null
    private var checking = false
    private var started = false
    private var cameraEpoch = 0L
    private var cameraReady = false
    private var cameraProvider: ProcessCameraProvider? = null
    private var capture: VideoCapture<Recorder>? = null
    private var recording: Recording? = null
    private var clip: File? = null
    private var clipSeconds = 0.0
    private var clipLanguage = "en"
    private var clipEndpoint: Endpoint? = null
    private var consentDialog: AlertDialog? = null
    private lateinit var endpointInput: EditText
    private lateinit var languagePicker: Spinner
    private lateinit var capabilityText: TextView
    private lateinit var statusText: TextView
    private lateinit var preview: PreviewView
    private lateinit var checkButton: Button
    private lateinit var cameraButton: Button
    private lateinit var recordButton: Button
    private lateinit var uploadButton: Button
    private lateinit var cancelButton: Button
    private lateinit var transcriptInput: EditText
    private val codes = listOf("en", "zh")
    private val preferences by lazy { getSharedPreferences("settings", MODE_PRIVATE) }
    private val clipsDirectory by lazy { File(cacheDir, "silent-clips").apply { mkdirs() } }
    private val maxStop = Runnable { stopRecording() }

    private val cameraPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) bindCamera() else {
            status("Camera permission is off. Enable it to record, or open this app's settings if Android no longer prompts.")
            render()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Clips are deliberately not restored across process death or rotation.
        clipsDirectory.listFiles()?.forEach { it.delete() }
        buildUi()
        endpointInput.setText(preferences.getString("endpoint", ""))
        transcriptInput.setText(savedInstanceState?.getString("transcript").orEmpty())
        endpointInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                invalidateRequest()
                checking = false
                capabilities = null
                verifiedEndpoint = null
                status("Check this server before recording")
                render()
            }
            override fun afterTextChanged(s: Editable?) = Unit
        })
        render()
    }

    private fun buildUi() {
        val outer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(12), dp(20), dp(20))
            setBackgroundColor(0xFFF6F8F6.toInt())
        }
        ViewCompat.setOnApplyWindowInsetsListener(outer) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(dp(20) + bars.left, dp(12) + bars.top, dp(20) + bars.right, dp(20) + bars.bottom)
            insets
        }
        val scroll = ScrollView(this).apply { addView(outer); isFillViewport = true }
        setContentView(scroll)
        fun label(value: String, size: Float = 16f): TextView = TextView(this).apply {
            text = value; textSize = size; setTextColor(0xFF173B30.toInt())
            setPadding(0, dp(8), 0, dp(6)); outer.addView(this)
        }
        label("Lip Input", 28f)
        label("Silent video → editable text", 18f)
        label("Face the camera in good light and speak naturally. Lipreading can be wrong; review every result. English and Mandarin depend on the server's installed models.", 14f)
        label("1  Choose a trusted server", 18f)
        endpointInput = EditText(this).apply {
            hint = "https://your-server.example"; contentDescription = "HTTPS recognition server"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_URI
            isSingleLine = true; importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO
            outer.addView(this, fullWidth())
        }
        checkButton = Button(this).apply { text = "Check server"; setOnClickListener { checkCapabilities() }; outer.addView(this) }
        languagePicker = Spinner(this).apply {
            contentDescription = "Recognition language"
            adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item,
                listOf("English (en)", "普通话 · Mandarin (zh)"))
            onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) { render() }
                override fun onNothingSelected(parent: AdapterView<*>?) = Unit
            }
            outer.addView(this, fullWidth())
        }
        capabilityText = label("Check a server to see its actual model availability", 14f)
        label("2  Record a short silent clip", 18f)
        preview = PreviewView(this).apply {
            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
            scaleType = PreviewView.ScaleType.FILL_CENTER
            contentDescription = "Front camera preview"
            outer.addView(this, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(270)))
        }
        label("Only the camera is used. No microphone permission or audio track. Clips stay in this app's temporary storage until you choose Upload.", 14f)
        cameraButton = Button(this).apply { text = "Enable camera"; setOnClickListener { enableCamera() }; outer.addView(this) }
        recordButton = Button(this).apply {
            text = "Record silent clip"; setOnClickListener {
                if (flow.phase == CaptureFlow.Phase.RECORDING) stopRecording() else startRecording()
            }; outer.addView(this)
        }
        uploadButton = Button(this).apply { text = "Review upload"; setOnClickListener { confirmUpload() }; outer.addView(this) }
        cancelButton = Button(this).apply {
            text = "Cancel and delete clip"; setOnClickListener { cancelEverything("Canceled. Local clip deleted."); render() }
            outer.addView(this)
        }
        statusText = label("Enter your recognition server to begin", 14f).apply {
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        }
        label("3  Review and edit", 18f)
        transcriptInput = EditText(this).apply {
            hint = "Your transcript will appear here"; contentDescription = "Editable transcript"
            minLines = 3; gravity = android.view.Gravity.TOP
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
            importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO
            outer.addView(this, fullWidth())
        }
        val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; outer.addView(this) }
        actions.addView(Button(this).apply {
            text = "Copy text"; setOnClickListener {
                val value = transcriptInput.text.toString()
                if (value.isBlank()) status("There is no text to copy yet") else {
                    getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText("Lip Input transcript", value))
                    status("Edited text copied")
                }
            }
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        actions.addView(Button(this).apply {
            text = "Share text"; setOnClickListener {
                val value = transcriptInput.text.toString()
                if (value.isBlank()) status("There is no text to share yet") else {
                    startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
                        type = "text/plain"; putExtra(Intent.EXTRA_TEXT, value)
                    }, "Share reviewed text"))
                }
            }
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        label("Prototype: server-based visual speech recognition, not an Android keyboard. Do not use unreviewed output for medical, legal, financial, or emergency decisions.", 12f)
    }

    private fun checkCapabilities() {
        if (flow.phase != CaptureFlow.Phase.IDLE || checking) return
        val endpoint = try { Endpoint.parse(endpointInput.text.toString()) } catch (e: IllegalArgumentException) {
            status(e.message ?: "Invalid server URL"); return
        }
        invalidateRequest()
        val requestId = requestGate.next()
        checking = true
        capabilities = null
        verifiedEndpoint = null
        status("Checking model availability… No video is sent.")
        render()
        call = api.capabilities(endpoint) { result -> runOnUiThread {
            if (!started || !requestGate.accepts(requestId)) return@runOnUiThread
            call = null
            checking = false
            result.fold(onSuccess = {
                capabilities = it
                verifiedEndpoint = endpoint
                preferences.edit().putString("endpoint", endpoint.base).apply()
                status("Server checked. Select an available language, then record.")
            }, onFailure = { status("Could not check server: ${it.message.orEmpty()}") })
            render()
        } }
    }

    private fun enableCamera() {
        if (hasCameraPermission()) { bindCamera(); return }
        if (preferences.getBoolean("askedCamera", false) && !shouldShowRequestPermissionRationale(Manifest.permission.CAMERA)) {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
        } else {
            preferences.edit().putBoolean("askedCamera", true).apply()
            cameraPermission.launch(Manifest.permission.CAMERA)
        }
    }

    private fun bindCamera() {
        if (!started || !hasCameraPermission()) return
        val epoch = ++cameraEpoch
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            if (!started || epoch != cameraEpoch) return@addListener
            try {
                val provider = future.get()
                cameraProvider = provider
                require(provider.hasCamera(CameraSelector.DEFAULT_FRONT_CAMERA)) { "No front camera is available" }
                val recorder = Recorder.Builder().setQualitySelector(
                    QualitySelector.from(Quality.HD, FallbackStrategy.lowerQualityOrHigherThan(Quality.HD))
                ).build()
                val video = VideoCapture.withOutput(recorder)
                val view = Preview.Builder().build().also { it.setSurfaceProvider(preview.surfaceProvider) }
                provider.unbindAll()
                provider.bindToLifecycle(this, CameraSelector.DEFAULT_FRONT_CAMERA, view, video)
                capture = video
                cameraReady = true
            } catch (e: Exception) {
                cameraReady = false
                capture = null
                status("Camera unavailable: ${e.message.orEmpty()}")
            }
            render()
        }, ContextCompat.getMainExecutor(this))
    }

    @android.annotation.SuppressLint("MissingPermission") // Checked before binding and recording.
    private fun startRecording() {
        if (flow.phase != CaptureFlow.Phase.IDLE || checking || !cameraReady || !hasCameraPermission()) return
        val endpoint = verifiedEndpoint ?: return
        val caps = capabilities ?: return
        val language = selectedLanguage()
        if (caps.language(language)?.available != true) return
        val video = capture ?: return
        (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).hideSoftInputFromWindow(endpointInput.windowToken, 0)
        val id = flow.beginRecording()
        try {
            val file = File.createTempFile("silent-", ".mp4", clipsDirectory)
            clip = file
            clipEndpoint = endpoint
            clipLanguage = language
            clipSeconds = 0.0
            val options = FileOutputOptions.Builder(file)
                .setDurationLimitMillis(caps.maxSeconds * 1000L)
                .setFileSizeLimit(LipApi.MAX_UPLOAD_BYTES)
                .build()
            // Intentionally do not call withAudioEnabled(): the MP4 has video only.
            recording = video.output.prepareRecording(this, options).start(ContextCompat.getMainExecutor(this)) { event ->
                if (id != flow.generation || !started) {
                    if (event is VideoRecordEvent.Finalize) file.delete()
                    return@start
                }
                when (event) {
                    is VideoRecordEvent.Start -> status("Recording silently. Speak for 1–${caps.maxSeconds} seconds, then tap Stop.")
                    is VideoRecordEvent.Status -> {
                        clipSeconds = event.recordingStats.recordedDurationNanos / 1_000_000_000.0
                        status("Recording ${String.format(Locale.ROOT, "%.1f", clipSeconds)} / ${caps.maxSeconds} seconds")
                    }
                    is VideoRecordEvent.Finalize -> {
                        handler.removeCallbacks(maxStop)
                        recording = null
                        clipSeconds = event.recordingStats.recordedDurationNanos / 1_000_000_000.0
                        val validEnd = !event.hasError() || event.error in setOf(
                            VideoRecordEvent.Finalize.ERROR_DURATION_LIMIT_REACHED,
                            VideoRecordEvent.Finalize.ERROR_FILE_SIZE_LIMIT_REACHED)
                        if (!validEnd || clipSeconds < 1.0 || !file.isFile || file.length() == 0L) {
                            cancelEverything(if (clipSeconds < 1.0) "Clip too short. Record at least one second." else "Recording failed. Please try again.")
                        } else if (flow.finishRecording(id)) {
                            status("Silent clip ready (${String.format(Locale.ROOT, "%.1f", clipSeconds)} s). Nothing uploaded yet.")
                        }
                        render()
                    }
                }
            }
            handler.postDelayed(maxStop, caps.maxSeconds * 1000L + 500)
            render()
        } catch (e: Exception) {
            cancelEverything("Could not record: ${e.message.orEmpty()}")
            render()
        }
    }

    private fun stopRecording() {
        if (!flow.stopRecording(flow.generation)) return
        recording?.stop()
        handler.removeCallbacks(maxStop)
        status("Finishing silent clip…")
        render()
    }

    private fun confirmUpload() {
        if (flow.phase != CaptureFlow.Phase.READY || consentDialog != null) return
        val endpoint = clipEndpoint ?: return
        val id = flow.generation
        val languageName = if (clipLanguage == "zh") "Mandarin (zh)" else "English (en)"
        consentDialog = AlertDialog.Builder(this)
            .setTitle("Upload this silent video?")
            .setMessage("Send this ${String.format(Locale.ROOT, "%.1f", clipSeconds)}-second video of your face to:\n\n${endpoint.route("transcriptions")}\n\nLanguage: $languageName\nModel: ${capabilities?.model}\n\nThis server can see your video. Only use a server you trust; its operator controls retention. No audio is included. Canceling cannot recall video bytes already sent.")
            .setNegativeButton("Keep local") { _, _ -> }
            .setPositiveButton("Upload once") { _, _ -> upload(id, endpoint) }
            .create().also { dialog ->
                dialog.setOnDismissListener { consentDialog = null }
                dialog.show()
            }
    }

    private fun upload(id: Long, endpoint: Endpoint) {
        val file = clip ?: return
        if (!started || !flow.consentAndUpload(id)) return
        invalidateRequest()
        val requestId = requestGate.next()
        status("Uploading and recognizing… First use can take up to 3 minutes.")
        render()
        try {
            call = api.transcribe(endpoint, file, clipLanguage) { result -> runOnUiThread {
                if (!started || !requestGate.accepts(requestId) || id != flow.generation) return@runOnUiThread
                call = null
                result.fold(onSuccess = { transcript ->
                    if (flow.uploadSucceeded(id)) {
                        deleteClip()
                        transcriptInput.setText(transcript.text)
                        status(if (transcript.text.isBlank()) "The model returned no text. Try another clip." else "Transcript from ${transcript.model}. Review and edit before sharing.")
                    }
                }, onFailure = {
                    if (flow.uploadFailed(id)) status("Recognition failed: ${it.message.orEmpty()}\nClip kept locally. Retry asks for upload consent again.")
                })
                render()
            } }
        } catch (e: Exception) {
            flow.uploadFailed(id)
            status("Could not upload: ${e.message.orEmpty()}")
            render()
        }
    }

    private fun cancelEverything(message: String) {
        invalidateRequest()
        checking = false
        consentDialog?.dismiss()
        consentDialog = null
        flow.cancel() // Invalidate before stop: Finalize from this recording must not revive the clip.
        handler.removeCallbacks(maxStop)
        recording?.stop()
        recording = null
        deleteClip()
        status(message)
    }
    private fun invalidateRequest() {
        requestGate.invalidate()
        call?.cancel()
        call = null
    }
    private fun deleteClip() { clip?.delete(); clip = null; clipEndpoint = null; clipSeconds = 0.0 }
    private fun selectedLanguage() = codes.getOrElse(languagePicker.selectedItemPosition) { "en" }
    private fun hasCameraPermission() = ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
    private fun status(value: String) { if (::statusText.isInitialized) statusText.text = value }
    private fun fullWidth() = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    private fun render() {
        if (!::cancelButton.isInitialized) return
        val idle = flow.phase == CaptureFlow.Phase.IDLE
        val cap = capabilities?.language(selectedLanguage())
        endpointInput.isEnabled = idle && !checking
        languagePicker.isEnabled = idle && !checking
        checkButton.isEnabled = idle && !checking
        checkButton.text = if (checking) "Checking…" else "Check server"
        cameraButton.visibility = if (cameraReady) View.GONE else View.VISIBLE
        cameraButton.isEnabled = idle && !checking
        cameraButton.text = if (hasCameraPermission()) "Retry camera" else "Enable camera"
        capabilityText.text = when {
            capabilities == null -> "Check a server to see its actual model availability"
            cap?.available == true -> "Available · ${cap.label}\nModel: ${capabilities!!.model}\nMaximum clip: ${capabilities!!.maxSeconds} seconds"
            else -> "Unavailable · ${if (selectedLanguage() == "zh") "Mandarin" else "English"}\n${cap?.reason ?: "This server does not offer this language"}"
        }
        recordButton.text = if (flow.phase == CaptureFlow.Phase.RECORDING) "Stop recording" else "Record silent clip"
        recordButton.isEnabled = flow.phase == CaptureFlow.Phase.RECORDING ||
            (idle && !checking && cameraReady && cap?.available == true)
        uploadButton.visibility = if (flow.phase == CaptureFlow.Phase.READY) View.VISIBLE else View.GONE
        cancelButton.visibility = if (!idle || checking) View.VISIBLE else View.GONE
        cancelButton.text = if (checking) "Cancel server check" else "Cancel and delete clip"
    }

    override fun onStart() {
        super.onStart()
        started = true
        if (hasCameraPermission()) bindCamera()
        render()
    }
    override fun onStop() {
        started = false
        cameraEpoch++
        val hadWork = flow.phase != CaptureFlow.Phase.IDLE || checking
        cancelEverything(if (hadWork) "Stopped when you left the screen. Local clip deleted." else statusText.text.toString())
        cameraProvider?.unbindAll()
        cameraReady = false
        capture = null
        super.onStop()
    }
    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString("transcript", transcriptInput.text.toString())
        super.onSaveInstanceState(outState)
    }
}
