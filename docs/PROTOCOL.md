# API contract / 接口约定

The Android client treats the configured endpoint as a server origin/base URL. Both calls use the same endpoint. HTTPS is required; redirects, embedded credentials, query strings and fragments must be rejected by the client so a recording is not silently redirected to another recipient.

客户端使用同一服务地址查询能力和上传视频。必须使用 HTTPS，禁止重定向、URL 内凭据、查询参数及片段，防止视频被悄悄转发给其他接收方。

## GET /v1/capabilities

```json
{
  "languages": [
    {"code": "en", "label": "English", "available": false, "reason": "Model is not configured"},
    {"code": "zh", "label": "Mandarin Chinese", "available": false, "reason": "Model is not configured"}
  ],
  "model": "model adapter identifier",
  "max_duration_seconds": 15
}
```

Only select an available language. The server remains authoritative and rechecks availability during upload. The capability response is not recognition output or an accuracy certification. Do not infer Mandarin support just because English works, or vice versa.

仅选择可用语言，服务端在上传时再次检查。能力查询不等于识别结果或准确率认证，英语成功也不证明普通话模型有效。

## POST /v1/transcriptions

`multipart/form-data` fields:

- `video`: one silent MP4 recording
- `language`: explicit `en` or `zh`

The user must approve upload of this specific clip to this endpoint before sending any video bytes. Return only real model output:

```json
{"text": "actual unedited model hypothesis", "language": "en", "model": "model/config identity"}
```

Errors use non-2xx status and structured detail:

```json
{"detail": {"code": "model_unavailable", "message": "Actionable reason"}}
```

Clients must not substitute placeholder speech when a request fails or returns empty text. Retry is a new operation; cancel invalidates the prior operation so late results cannot overwrite newer work. Closing the connection signals client cancellation, but cannot guarantee a server has not already received the upload.

错误或空结果不能替换成示例话术。重试为新操作；取消后旧结果不得覆盖新任务。关闭连接仅表示客户端取消，不保证服务端尚未收到视频。
