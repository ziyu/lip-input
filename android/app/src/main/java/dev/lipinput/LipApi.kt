package dev.lipinput

import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.asRequestBody
import okio.BufferedSink
import okhttp3.Response
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit

data class LanguageCapability(val code: String, val label: String, val available: Boolean, val reason: String?)
data class Capabilities(val languages: List<LanguageCapability>, val model: String, val maxSeconds: Int) {
    fun language(code: String) = languages.firstOrNull { it.code == code }
}
data class Transcript(val text: String, val language: String, val model: String)

class LipApi internal constructor(builder: OkHttpClient.Builder = OkHttpClient.Builder()) {
    // A redirect could change the recipient the user consented to. Never follow one, including HTTPS->HTTPS.
    internal val client = builder
        .followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(150, TimeUnit.SECONDS)
        .writeTimeout(40, TimeUnit.SECONDS)
        .callTimeout(180, TimeUnit.SECONDS)
        .build()

    fun capabilities(endpoint: Endpoint, callback: (Result<Capabilities>) -> Unit): Call =
        enqueue(Request.Builder().url(endpoint.route("capabilities")).get().build(), callback, ::parseCapabilities)

    fun transcribe(endpoint: Endpoint, video: File, language: String, callback: (Result<Transcript>) -> Unit): Call {
        require(language in setOf("en", "zh"))
        require(video.isFile && video.length() in 1..MAX_UPLOAD_BYTES) { "Clip is empty or exceeds the 20 MiB limit" }
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("language", language)
            .addFormDataPart("video", "clip.mp4", video.asRequestBody("video/mp4".toMediaType()))
            .build()
        // Even HTTP 503 + Retry-After: 0 must not replay a clip without fresh user consent.
        val once = object : RequestBody() {
            override fun contentType() = body.contentType()
            override fun contentLength() = body.contentLength()
            override fun isOneShot() = true
            override fun writeTo(sink: BufferedSink) = body.writeTo(sink)
        }
        return enqueue(Request.Builder().url(endpoint.route("transcriptions")).post(once).build(), callback) {
            parseTranscript(it, language)
        }
    }

    private fun <T> enqueue(request: Request, callback: (Result<T>) -> Unit, parse: (JSONObject) -> T): Call {
        val call = client.newCall(request)
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) { callback(Result.failure(e)) }
            override fun onResponse(call: Call, response: Response) {
                val result = runCatching {
                    response.use {
                        if (it.code in 300..399) throw IOException("Redirect refused. Use the server's final HTTPS URL and check again.")
                        val body = it.body ?: throw IOException("Empty server response")
                        if (body.contentLength() > MAX_RESPONSE_BYTES) throw IOException("Server response is too large")
                        val source = body.source()
                        source.request(MAX_RESPONSE_BYTES + 1)
                        if (source.buffer.size > MAX_RESPONSE_BYTES) throw IOException("Server response is too large")
                        val content = source.readUtf8()
                        if (!it.isSuccessful) {
                            val detail = runCatching { JSONObject(content).optJSONObject("detail") }.getOrNull()
                            val message = detail?.optString("message")?.takeIf { value -> value.isNotBlank() }?.take(500)
                            throw IOException(message ?: "Server request failed (HTTP ${it.code})")
                        }
                        parse(JSONObject(content))
                    }
                }
                callback(result)
            }
        })
        return call
    }

    companion object {
        const val MAX_UPLOAD_BYTES = 20L * 1024 * 1024
        private const val MAX_RESPONSE_BYTES = 512L * 1024
        fun parseTranscript(json: JSONObject, expectedLanguage: String): Transcript {
            val text = json.getString("text")
            require(text.isNotBlank()) { "Server returned an empty transcript" }
            require(text.length <= 100_000) { "Server returned an oversized transcript" }
            val language = json.getString("language")
            require(language == expectedLanguage) { "Server returned a different language" }
            val model = json.getString("model")
            require(model.isNotBlank()) { "Server did not identify its model" }
            return Transcript(text, language, model)
        }
        fun parseCapabilities(json: JSONObject): Capabilities {
            val maxSeconds = json.getInt("max_duration_seconds")
            require(maxSeconds in 1..120) { "Unsupported server recording limit" }
            val all = json.getJSONArray("languages")
            val languages = (0 until all.length()).map { index ->
                val item = all.getJSONObject(index)
                LanguageCapability(item.getString("code"), item.getString("label"),
                    item.getBoolean("available"), item.optString("reason").takeUnless { it.isBlank() || it == "null" })
            }.filter { it.code in setOf("en", "zh") }
            require(languages.distinctBy { it.code }.size == languages.size) { "Duplicate language capabilities" }
            val model = json.getString("model")
            require(model.isNotBlank()) { "Server did not identify its model" }
            return Capabilities(languages, model, minOf(maxSeconds, 15))
        }
    }
}
