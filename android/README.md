# Lip Input Android

Native Kotlin/CameraX client for the backend in `../server`. This is a prototype, not a system keyboard or an offline recognizer. Recognition only works when the server reports a real installed model available. It never substitutes demo text.

## Build

Use Android Studio Ladybug or later, JDK 17+, Android SDK platform 35, and build tools 35.0.0. Gradle wrapper pins Gradle 8.9; AGP is 8.7.3 and Kotlin 2.0.21. Source/bytecode target is Java 17; minSdk 26.

Accept Android SDK terms yourself before installing required SDK components: https://developer.android.com/studio/terms

Core endpoint, protocol, and state tests can run without any Android SDK installation:

```sh
./gradlew -p core-tests test
```

Full Android build and lint:

```sh
export ANDROID_HOME=/path/to/Android/Sdk
./gradlew testDebugUnitTest lintDebug assembleDebug
./gradlew connectedDebugAndroidTest  # attached emulator/device required
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

APK output: `app/build/outputs/apk/debug/app-debug.apk`. No release keystore is included. HTTPS uses Android system certificate authorities; self-signed certificates are deliberately not bypassed. To test a local backend, expose it through an HTTPS reverse proxy with a trusted certificate. HTTP emulator loopback URLs are rejected.

## Use and privacy

1. Enter the trusted server base URL, for example `https://lip.example.org` or `https://example.org/lip`. Do not append `/v1`; the app adds it. No credentials, query strings, fragments, encoded paths, or redirects are accepted.
2. Tap **Check server**. This sends only a capability GET. Choose English (`en`) or Mandarin (`zh`); record is enabled only if that language is available.
3. Enable the front camera, speak naturally for 1–15 seconds, and tap **Stop recording**. The server can lower the duration limit. Recording also stops automatically and is capped at 20 MiB.
4. Tap **Review upload**. The confirmation identifies the exact HTTPS recipient, language, and model. **Keep local** sends nothing. **Upload once** sends the silent MP4. Every retry requires a fresh confirmation.
5. Edit the returned text, then copy or share it explicitly. Sharing opens Android's chooser with text only.

There is no microphone permission and `withAudioEnabled()` is never called. Clips are private cache files, never gallery/media-store exports. Successful recognition, Cancel, or leaving the screen deletes the local clip. Rotation also cancels and deletes a clip; edited transcript is retained across ordinary Activity recreation. On process restart stale cache clips are deleted. The server controls retention of uploaded bytes; cancellation cannot recall data already sent. Endpoint preference is stored locally; transcripts are not persisted in preferences or app backups. A system saved-state bundle may temporarily hold the edited transcript across Activity recreation.

## Verification coverage

Unit tests cover strict endpoint validation, capability parsing and unavailable languages, redirect/retry flags, per-clip upload transitions, cancellation, and stale callback suppression. A test-only local HTTPS server verifies multipart fields, redirect refusal, malformed responses, and no automatic video replay on HTTP 503 with `Retry-After: 0`. Device instrumentation checks the merged app permissions contain neither microphone nor storage permissions. There is no connected device in the initial build environment, so camera hardware behavior is a manual acceptance gate.

On a real Android 8+ front-camera device test:

- Deny camera once and permanently; app stays usable and offers retry/settings
- Grant camera, switch apps, return; preview is re-bound without old callbacks reviving work
- Check bad HTTPS URL, HTTP URL, unavailable backend, missing model, disabled Mandarin; never enable unsupported recognition
- Record <1 second, normal 3–5 seconds, automatic duration limit, repeated Stop, and Cancel while recording/finalizing
- Inspect MP4 using `ffprobe`: one video stream, no audio stream; lips remain fully in frame; actual front camera orientation is correct
- Decline upload; server logs must show no POST. Confirm once; server receives fields `video` + `language`
- Double tap upload; only one confirmation/request. Retry after timeout/429/503 requires new consent
- Rotate/background/back during recording, confirmation, and upload; local cache clip removed and stale callbacks ignored
- HTTPS 301/302/307/308 must not be followed (including same-host redirects)
- Edit/copy/share transcript; shared payload contains only edited text, not video
- Validate non-Latin Mandarin text, large-font layout, TalkBack labels, and keyboard/inset behavior

Accuracy/latency and end-to-end recognition on actual English/Mandarin speech remain unverified until licensed/configured checkpoints and device test clips are available.
