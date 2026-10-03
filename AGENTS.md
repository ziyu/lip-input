# Contributor guide

## Layout

- `android/`: native Kotlin/CameraX app, Gradle 8.9, AGP 8.7.3, Kotlin 2.0.21, JDK 17, SDK 35
- `server/`: Python 3.11+ FastAPI transport and explicit mpc001 visual-only model adapter
- `docs/VALIDATION.md`: distinguish automated checks from device/model release gates

## Checks

```sh
python -m pip install -r server/requirements-dev.txt
python -m pytest server/tests -q
cd android
./gradlew --no-daemon testDebugUnitTest lintDebug assembleDebug
```

FFmpeg/ffprobe are required for backend media tests. The Android SDK requires its terms to be accepted by the operator; never silently accept SDK or model terms. Android CI is manually gated for that reason. Use installed tools when possible; do not commit build tools or downloaded SDKs.

## Invariants

- No microphone permission, audio-enabled recording or synthetic transcript fallback
- User chooses a language; never substitute another language model silently
- Obtain explicit per-clip consent before upload to the selected HTTPS endpoint
- Reject redirects, cleartext HTTP and embedded URL credentials
- Cancellation invalidates all stale results and cleans up local/server temporary data
- No weights, private videos, credentials, private keys or checkpoints in git
- Real model integration follows the pinned upstream language-specific preprocessing/decoder; configuration alone does not verify inference accuracy
- Test doubles must be isolated to tests and unmistakably labeled
- Test denied camera/microphone conditions, no-face/short/audio-free clips, repeated requests, cancellation and lifecycle interruption
- Do not claim a build, device test or real model inference passed unless it actually ran

Before publishing, fetch latest `main`, preserve concurrent changes, and verify CI for the exact resulting commit. Do not deploy publicly, provision paid resources or change model licensing without authorization.
