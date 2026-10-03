# Lip Input / 唇语输入

Android-first, silent-video visual speech input prototype. **Real recognition is not verified yet.** The native app records video without microphone access and can send it, with your explicit consent, to a server you operate. English and Mandarin are separate model capabilities, not translated UI labels. Without a configured real model the server reports recognition unavailable; it never fabricates a transcript.

Android 原生无声视频唇语输入原型。**真实识别尚未验证。** 手机无需麦克风权限，视频只有在你逐次确认后才上传到自己管理的服务器。英语、普通话是分别配置的真实模型能力，并非仅翻译界面。模型未配置时会明确显示不可用，不生成虚假结果。

## What is included / 本版内容

- Native Android front-camera preview and bounded silent recording
- Explicit language selection based on backend availability
- Editable transcript, copy and Android share sheet
- Per-clip upload approval, HTTPS endpoint validation, cancellation and retries
- Self-hosted Python API with documented upstream model adapter, bounded jobs, temporary file cleanup and honest capability reporting
- Automated tests, CI, and separate real-device / real-model validation checklist

This is a recording/transcription app, **not yet an Android system keyboard (IME)** or on-device/streaming recognition. Results are uncertain and must be reviewed. The visual signal alone cannot uniquely distinguish many spoken words.

当前为录制转写 App，**尚非 Android 系统输入法（IME）**，也不是端侧或实时流式识别。唇形存在歧义，结果必须人工确认。

## Repository / 目录

- [`android/`](android/) — Android app, build and client tests
- [`server/`](server/) — API, real-model adapter and backend tests
- [`docs/VALIDATION.md`](docs/VALIDATION.md) — release gates and real inference evidence requirements
- [`.github/workflows/ci.yml`](.github/workflows/ci.yml) — automatic backend checks plus manually authorized Android build/lint/unit tests

## Quick start / 开始使用

### Android

Use Android Studio with JDK 17, Android SDK 35, Gradle 8.9. Review and accept the [Android SDK terms](https://developer.android.com/studio/terms) yourself before installing the SDK. Open `android/`, sync, and run on a real camera-equipped Android device (Android 8 / API 26 or newer).

使用 Android Studio、JDK 17、Android SDK 35、Gradle 8.9。安装 SDK 前请自行阅读并接受 [Android SDK 条款](https://developer.android.com/studio/terms)。打开 `android/` 并在 Android 8 以上真机运行。

```sh
cd android
./gradlew --no-daemon testDebugUnitTest lintDebug assembleDebug
# APK: app/build/outputs/apk/debug/app-debug.apk
```

The Android CI job is manual: use Actions → Validate → Run workflow and affirm SDK terms only after reviewing them. Push/PR events run backend and JVM client-core tests without accepting Android SDK terms.

Android CI 需手动触发并确认 SDK 条款；推送和 PR 自动运行后端和 JVM 客户端核心测试，不自动接受 SDK 条款。

No microphone permission is needed. Set your own HTTPS backend address, refresh capabilities, choose an available language, record, stop, and approve that specific upload. Review/edit the result before copying or sharing. Cancel or leave the screen to stop work. A TLS certificate trusted by Android is required; do not disable TLS checks.

无需麦克风权限。填写自己的 HTTPS 服务地址，刷新模型能力，选择可用语言，录制、停止，确认本次上传。复制或分享前检查修改文本。取消或离开页面会停止操作。服务需使用 Android 信任的 TLS 证书，不能关闭证书验证。

### Backend and models / 后端和模型

See [`server/README.md`](server/README.md) for exact installation, configuration and adapter commands. Start without model configuration to inspect unavailable capabilities safely. Dependencies come from package registries; upstream research code and checkpoint installation are operator-managed steps after reviewing their licenses. No weights, secrets, paid provider, automatic research-code installer or public deployment are included.

后端安装、配置与适配器命令见 [`server/README.md`](server/README.md)。未配置模型时可启动服务检查不可用原因。上游研究代码和权重需运营者审查许可后自行安装。本仓库不包含权重、凭据、付费服务或自动部署。

The initial adapter targets the official [Visual Speech Recognition for Multiple Languages](https://github.com/mpc001/Visual_Speech_Recognition_for_Multiple_Languages) implementation, using separate English/Mandarin configurations and each model's own preprocessing/decoder. Upstream code/checkpoints have research/comparison and non-commercial restrictions; this repository does not grant rights to them. Availability means runtime configuration is present, not that accuracy has been established for your clips. Track actual verification separately in the release checklist.

初始适配器面向官方多语言视觉语音识别实现，英语和普通话使用独立配置及各自的预处理和解码器。上游代码与权重具有研究、对比评测及非商业限制，本仓库不授予这些资源的使用权。“可用”表示运行配置就绪，不代表已验证你的视频能准确识别。

## Privacy and security / 隐私与安全

Video contains your face and mouth. Only send recordings to a server you control and trust. Consent is scoped to each clip and chosen endpoint. The application requests camera/network access, never microphone access; copy/share happens only on user action. App recordings and server upload files are temporary. Cancellation prevents stale results from being displayed, but an upload already received by a server cannot be recalled; server operators are responsible for retention, access controls and log policy.

视频包含人脸与口部信息，只应上传到自己信任和控制的服务。授权针对本次视频和选定地址。App 不申请麦克风权限；复制/分享由用户主动操作。临时视频会清理，但已被服务接收的数据无法通过取消“撤回”，服务运营者需承担访问控制、日志和数据保留责任。

Bind the API locally and put it behind a trusted HTTPS reverse proxy or private network. Do not expose an unauthenticated development API to the Internet. Do not commit faces/videos, checkpoints, TLS private keys or credentials. If you add authentication, never place secrets in URL query strings.

后端默认仅应本地监听，通过可信 HTTPS 反向代理或私有网络访问，不要将无认证开发接口公开到互联网。禁止提交个人视频、权重、TLS 私钥或凭据。

## Verification status / 验证状态

See the implementation handoff and CI for exact test results. The checklist intentionally separates deterministic tests from real camera, model and accuracy validation. No commercial-readiness, multilingual accuracy, latency or on-device performance claim is made.

具体测试结果以当前提交的 CI 与交付说明为准。清单区分自动测试、真机摄像头及真实模型准确率验证，不能据此宣称商业可用、准确率、延迟或端侧性能。
