# Validation / 验证

Unit/contract tests are not evidence of lip-reading accuracy. A built APK is not evidence of working inference. No model inference has been verified by this repository's initial implementation.

单元测试不代表唇语识别准确率，APK 构建成功不代表真实推理通过。本项目初版尚未完成真实模型推理验证。

## Release gates / 发布前验证

- [ ] Run Android unit tests, lint and debug build on exact release commit
- [ ] On a real Android device deny camera permission, retry and grant; no microphone permission should be declared or requested
- [ ] Record an actually audio-free clip; inspect with `ffprobe` and assert no audio stream
- [ ] Background/rotate/close during recording and upload: no leaked video, crash or stale transcript
- [ ] Cancel upload, immediately record/upload again: older results never overwrite the new request
- [ ] Test endpoint rejection (HTTP, user info, query, fragment) and redirects, offline/timeouts/server errors
- [ ] Confirm video leaves device only after the per-clip upload consent dialog
- [ ] Run real English model on consenting speaker's held-out English silent videos
- [ ] Run real Mandarin model on consenting speaker's held-out Mandarin silent videos
- [ ] For each real language record model/config/checkpoint hashes, license permission, CPU/GPU, preprocessing versions, latency, reference text, raw hypothesis, edit distance and failures
- [ ] Test blank/no-face, multiple faces, short/long clips, occluded mouth and audio-free 1–3 second clips against actual adapters
- [ ] Confirm rejected/cancelled/completed uploads are removed from temporary storage

Use local, consenting adult test recordings. Do not commit identifiable videos, checkpoints or access credentials. Do not report test adapters or synthetic videos as successful real-model recognition.

使用获得同意的成年人本地录制素材，不要提交可识别个人的视频、模型权重或访问凭据。测试替身与合成视频不能用作真实识别验证。
