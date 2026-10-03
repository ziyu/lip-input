# Lip Input server / 服务端

This is an operator-hosted, visual-only research prototype. The HTTP service and
video-validation tests work without model weights. **Transcription is unavailable
by default. No model, weights, or upstream source are downloaded automatically.**
There are no sample transcripts, fallback speech APIs, or production mock modes.

这是由用户或管理员自行运行的纯视觉研究原型。默认不具备识别能力；必须先核实许可、
自行准备模型权重及兼容运行环境，再显式启用。没有假识别结果，也不会调用音频语音接口。

## Run the API safely

From the repository root, using Python 3.11 or newer:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r server/requirements.txt
python -m server
```

FFmpeg and ffprobe must be installed separately from their official/OS package
sources. `python -m server` binds only `127.0.0.1:8000`, disables access logs, uses
one worker, and does not trust forwarded headers. It does not open a firewall,
provision credentials, deploy anything, or publish a public URL. A local request:

```sh
curl http://127.0.0.1:8000/v1/capabilities
```

The Android client requires HTTPS with a trusted certificate. Use an
operator-managed HTTPS reverse proxy plus access control, upload/rate limits,
and timeouts. A VPN/approved private network is preferred for this prototype.
The Android prototype does not yet provide an API-key header UI, so use
network-level/VPN access control or an explicitly designed compatible gateway;
do not expose the unauthenticated backend directly to the Internet. Terminate
TLS externally and keep the upstream loopback-only. Do not disable certificate
validation. Allow at least 120 seconds after upload for cold model inference.
If using a URL prefix, the proxy must strip that prefix before forwarding.

正式接入手机时，需由管理员配置可信 HTTPS、访问控制和限流。不要直接公开此接口；
应用没有 API 密钥输入界面，建议先用受控私网/VPN。不要关闭证书校验。

## Exact API contract

GET `/v1/capabilities`:

```json
{
  "languages": [
    {"code": "en", "label": "English", "available": false, "reason": "Operator setup required..."},
    {"code": "zh", "label": "Mandarin Chinese", "available": false, "reason": "Operator setup required..."}
  ],
  "model": "mpc001-vsr-multilingual",
  "max_duration_seconds": 15.0
}
```

`reason` is null only when that language has successfully loaded its actual model
and detector in the configured runtime during startup. This is a readiness
check, not evidence of transcription accuracy. Languages are explicit, separate
checkpoints; there is no auto-detection or translation. Reconfigure/restart the
service after changing model files. A clip-specific inference error does not
permanently disable an otherwise healthy language.

POST `/v1/transcriptions`: `multipart/form-data` with exactly one file part named
`video` and one text part named `language`, either `en` or `zh`. No URL, external
landmark file, arbitrary model, or command can be supplied by the client.

```json
{"text": "actual model output", "language": "en", "model": "mpc001-vsr-multilingual:en"}
```

All errors use `{"detail":{"code":"...","message":"..."}}`. Typical codes:

- 400: `invalid_request`, `unsupported_language`
- 408: `upload_timeout`
- 413: `upload_too_large`
- 415: `invalid_video`, invalid multipart content type
- 422: `too_short`, `too_long`, `video_dimensions`, `no_face`, `no_speech`
- 429: `busy` with `Retry-After: 3`; retry requires the user's fresh upload consent
- 499: `cancelled` if the client disconnects while processing
- 503: `model_unavailable`, `runtime_unavailable`, `inference_failed`
- 504: `inference_timeout`

Accepted duration is 1–15 seconds. The service tolerates up to 50ms of container
timestamp rounding at the upper boundary; this is not extra recording time.
A clip must contain at least 25 decoded normalized frames. Upload size is at
most 20 MiB; raw multipart framing gets a separate 64 KiB allowance. Maximum
input dimension is 1920 pixels with at most 1920×1080 pixels, including portrait.
One video stream is required. MP4/MOV, WebM/Matroska, and AVI are accepted if
FFmpeg can decode them; untrusted filenames and declared MIME types are not used
to select commands. Container metadata and decoded frames are both checked.

## Real model adapter and licensing

The adapter targets the reviewed upstream revision
[`5e1405db0ae816509fb312f9a578724c2e0de0c7`](https://github.com/mpc001/Visual_Speech_Recognition_for_Multiple_Languages/commit/5e1405db0ae816509fb312f9a578724c2e0de0c7)
of [mpc001/Visual_Speech_Recognition_for_Multiple_Languages](https://github.com/mpc001/Visual_Speech_Recognition_for_Multiple_Languages).
Read-only source verification was performed on 2026-10-03. No upstream source or
checkpoint was installed or executed while building this prototype.

Important: the repository's top-level
[LICENSE](https://github.com/mpc001/Visual_Speech_Recognition_for_Multiple_Languages/blob/5e1405db0ae816509fb312f9a578724c2e0de0c7/LICENSE)
and README restrict its use to research/private study and comparative or
benchmarking purposes, separate from commercial development. Some individual
source headers say Apache 2.0; that does **not** establish commercial rights to
the whole repository, weights, training data, or resulting product. Obtain
appropriate permission for your actual use. This repository does not grant
those rights or accept any license on your behalf. Trusted checkpoint files can
contain executable pickle payloads when loaded by PyTorch; review provenance and
run the model environment under an unprivileged account without secrets.

上游仓库存在研究/比较评测用途限制，部分文件头的 Apache 声明不能代替对整个代码、
权重及数据许可的核实。本原型不能据此宣称可商用。启用变量只记录管理员的明确选择，
不是授予许可。请使用可信权重，并在无密钥、低权限的隔离环境运行。

### Separate visual-only models

- English (`en`): upstream
  [`configs/LRS3_V_WER19.1.ini`](https://github.com/mpc001/Visual_Speech_Recognition_for_Multiple_Languages/blob/5e1405db0ae816509fb312f9a578724c2e0de0c7/configs/LRS3_V_WER19.1.ini)
  references `benchmarks/LRS3/models/LRS3_V_WER19.1/model.pth` and `model.json`, plus
  `benchmarks/LRS3/language_models/lm_en_subword/model.pth` and `model.json`
- Mandarin (`zh`): upstream
  [`configs/CMLR_V_WER8.0.ini`](https://github.com/mpc001/Visual_Speech_Recognition_for_Multiple_Languages/blob/5e1405db0ae816509fb312f9a578724c2e0de0c7/configs/CMLR_V_WER8.0.ini)
  references `benchmarks/CMLR/models/CMLR_V_WER8.0/model.pth` and `model.json`, plus
  `benchmarks/CMLR/language_models/lm_zh/model.pth` and `model.json`

Both configs must retain `[input] modality=video`, input `v_fps=25`, and model
`v_fps=25`. The service rejects audio/audiovisual configs and missing asset paths.
Paths in the INI resolve relative to the upstream checkout, just as upstream
expects. Do not point the Mandarin setting at the English checkpoint or vice
versa; the operator owns this language/weight mapping.

The operator must manually obtain a reviewed checkout at the exact revision,
read the upstream installation directions, and provision trusted, licensed
checkpoints and language-model assets. There is intentionally no one-command
unreviewed model installer here.

### Runtime compatibility

Use a **separate** Python environment for upstream dependencies. Upstream's
README documents Python 3.8 and PyTorch/torchvision/torchaudio, then its own
requirements plus FFmpeg and a face tracker. The API itself uses Python 3.11+.
`LIP_RUNTIME_PYTHON` connects these environments through a fresh subprocess.

The actual source requires `mediapipe.solutions.face_detection`,
`torchvision.io.read_video`, PyAV, OpenCV, NumPy, SciPy, scikit-image, six, and the
repository's bundled `espnet` code. Recent releases can remove old APIs or alter
checkpoint loading, so blindly installing latest versions is not a verified
setup. Use compatible versions, review their licenses, and run the opt-in
acceptance tests below. No fully tested upstream dependency lockfile is claimed.
The startup probe actually imports and constructs the full pipeline and tracker;
missing/incompatible dependencies leave the language unavailable.

`LIP_DEVICE=cpu` is the default, including the MediaPipe tracker. A configured
CUDA device such as `cuda:0` is optional and must match the operator runtime.
CPU loading/decoding can exceed the 120-second budget, especially for English;
there is no real-time performance claim. Each request reloads its selected model
for deterministic cancellation and memory release, so GPU/CPU cold-start latency
is substantial. This design favors safe lifecycle handling over throughput.

### Explicit configuration example

After reviewing/provisioning the runtime and verifying your rights, export these
variables. Substitute actual local paths. `.env.example` is a template only; the
service does not silently load it.

```sh
export LIP_UPSTREAM_ROOT=/opt/lip-model/Visual_Speech_Recognition_for_Multiple_Languages
export LIP_RUNTIME_PYTHON=/opt/lip-model/venv/bin/python
export LIP_CONFIG_EN="$LIP_UPSTREAM_ROOT/configs/LRS3_V_WER19.1.ini"
export LIP_CONFIG_ZH="$LIP_UPSTREAM_ROOT/configs/CMLR_V_WER8.0.ini"
export LIP_DEVICE=cpu
export LIP_LICENSE_ACK=I_HAVE_VERIFIED_MY_RIGHTS
export LIP_ENABLE_UPSTREAM=1
python -m server
```

Both model probes run sequentially at startup and can each consume up to 120
seconds. One language can be available while the other remains unavailable.
Changing these settings does not install anything or expand network access.

### Preprocessing and exact interface

1. Probe the input with FFprobe; reject invalid streams, dimensions, duration,
   or size. Decode only the video stream and remove audio, subtitles, data and
   metadata. Normalize to 25fps and fit within 640×640 preserving aspect ratio;
   apply rotation metadata, normalize sample aspect ratio, and encode a private
   audio-free H.264 MP4. No audio is fed to any model
2. Construct the verified
   [`InferencePipeline`](https://github.com/mpc001/Visual_Speech_Recognition_for_Multiple_Languages/blob/5e1405db0ae816509fb312f9a578724c2e0de0c7/pipelines/pipeline.py)
   with the configured INI, `detector="mediapipe"`, `face_track=True`, and explicit
   device. Split its `forward` sequence into `process_landmarks(video, None)`,
   `dataloader.load_data(video, landmarks)`, then `model.infer(data)` so the
   adapter can reject missing tracks before upstream interpolation
3. Upstream
   [MediaPipe detection](https://github.com/mpc001/Visual_Speech_Recognition_for_Multiple_Languages/blob/5e1405db0ae816509fb312f9a578724c2e0de0c7/pipelines/detectors/mediapipe/detector.py)
   uses face keypoints. Require detections in at least 80% of normalized frames;
   map its documented no-face assertion to `no_face`
4. Upstream performs face alignment, grayscale 96×96 mouth crops, interpolation
   of short landmark gaps, then 88×88 center crops, scaling by 255, and
   normalization by mean 0.421/std 0.165. We use upstream
   [data loader](https://github.com/mpc001/Visual_Speech_Recognition_for_Multiple_Languages/blob/5e1405db0ae816509fb312f9a578724c2e0de0c7/pipelines/data/data_module.py)
   and [transforms](https://github.com/mpc001/Visual_Speech_Recognition_for_Multiple_Languages/blob/5e1405db0ae816509fb312f9a578724c2e0de0c7/pipelines/data/transforms.py),
   rather than reimplementing a guessed tensor transform
5. Return only actual nonempty decoded text. Empty output becomes `no_speech`;
   this does not prove detection of silent/non-speaking faces. Visual ambiguity
   can still produce incorrect words or hallucinations

单人正面、光线良好、嘴部清晰的视频最适合此原型。多人、侧脸、遮挡、语言不匹配和
自然无声口型都可能识别失败。训练数据中的有声讲话视频与用户主动无声说话存在分布
差异；没有证明本原型在真实无声输入场景中的准确率。必须由用户检查和编辑结果。

## Privacy and resource lifecycle

- Raw request size is bounded before multipart parsing, including streamed
  uploads without Content-Length. The upload deadline is 30 seconds
- One active upload/inference per ASGI worker by default; additional requests
  return 429 without queueing. Run one worker. A proxy must also rate-limit and
  constrain idle connections. This service alone is not an Internet perimeter
- Decoding/probing has a 30-second subprocess timeout; total video processing
  and inference has a 120-second deadline. Output is bounded
- FFmpeg accepts only local `file,pipe` protocols and specified video demuxers.
  No shell, user-provided command, or client URL is executed. Keep FFmpeg patched
- Client disconnect and coroutine cancellation cancel and await the job, kill
  its entire POSIX process group, and reap the direct process. A process group
  is killed even if its leader already exited
- Upload-parser temporary files are closed; per-request 0700 directories and
  0600 video files are removed on success, errors, timeout, and cancellation
- The service stores no clips/transcripts permanently and emits no access logs
  from the default launch command. API responses have `Cache-Control: no-store`.
  Configure the proxy to avoid body logging/caching and align its retention
- The server operator necessarily receives the uploaded face video. Avoid
  uploading another person's video without their permission. These controls are
  not a secure-erasure guarantee for disk, swap, proxy storage, or crash dumps
- Abrupt power loss or SIGKILL of the API process itself cannot run Python
  cleanup. Use a private encrypted temporary filesystem (`LIP_TEMP_DIR` and
  `TMPDIR`) and an operator-controlled cleanup policy. Multipart spooling uses
  Python's standard private temporary-file location, independently of LIP_TEMP_DIR

## Verification

Ordinary tests, with **no real model execution**:

```sh
python -m pip install -r server/requirements-dev.txt
python -m pytest server/tests -q
# Equivalent runner without installing pytest:
python -m unittest discover -s server/tests -v
```

Tests create real FFmpeg-encoded audio-free MP4s, decode and normalize them,
verify removal of audio in a separate synthetic clip, and exercise short/long,
corrupt, empty, duplicate-part, size-bound, missing-model, repeat, concurrency,
timeout and disconnect paths. Child-process timeout/cancellation tests spawn
small locally authored Python sleepers, including an exited leader with a live
descendant. Adapter-contract tests use explicitly labeled module doubles;
transcript/no-face injection is **not evidence of lip-reading accuracy**.

Two real-model acceptance tests are skipped unless the operator explicitly opts
in, has enabled the licensed runtime, and supplies consented audio-free English
and Mandarin clips. They test real no-face detection and nonempty real inference:

```sh
export LIP_RUN_REAL_MODEL_TESTS=1
export LIP_REAL_EN_VIDEO=/private/consented-english-silent.mp4
export LIP_REAL_ZH_VIDEO=/private/consented-mandarin-silent.mp4
python -m unittest server.tests.test_real_models -v
```

These tests require the upstream code and checkpoints to execute and may take
minutes. Nonempty output is not accuracy validation. Before using this beyond
research, evaluate a consented, held-out corpus with manually verified text,
report English WER and Mandarin CER separately, and measure target-device/network
latency, failure rate, accents and lighting variation. Do not substitute the
upstream dataset scores for this application's measured performance.
