package dev.lipinput

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class LipApiTest {
    @Test fun rejectsBlankOrMismatchedTranscripts() {
        listOf("", " ", "\n\t").forEach { text ->
            val json = JSONObject().put("text", text).put("language", "en").put("model", "real")
            assertThrows(IllegalArgumentException::class.java) { LipApi.parseTranscript(json, "en") }
        }
        assertThrows(IllegalArgumentException::class.java) {
            LipApi.parseTranscript(JSONObject().put("text", "hello").put("language", "en").put("model", "real"), "zh")
        }
    }
    @Test fun preservesMandarinTranscriptWithoutInventingText() {
        val value = LipApi.parseTranscript(JSONObject().put("text", "你好，世界").put("language", "zh").put("model", "real:zh"), "zh")
        assertEquals("你好，世界", value.text)
    }
    @Test fun neverFollowsRedirectsOrAutomaticallyRetriesVideo() {
        val client = LipApi().client
        assertFalse(client.followRedirects)
        assertFalse(client.followSslRedirects)
        assertFalse(client.retryOnConnectionFailure)
    }
    @Test fun onlyExplicitlyAvailableLanguagesCanBeUsed() {
        val caps = LipApi.parseCapabilities(JSONObject("""{"languages":[{"code":"en","label":"English","available":true,"reason":null},{"code":"zh","label":"Mandarin","available":false,"reason":"Checkpoint missing"}],"model":"real-model","max_duration_seconds":15}"""))
        assertTrue(caps.language("en")!!.available)
        assertFalse(caps.language("zh")!!.available)
        assertEquals("Checkpoint missing", caps.language("zh")!!.reason)
        assertNull(caps.language("xx"))
        assertEquals(15, caps.maxSeconds)
    }
    @Test fun recordingBoundNeverExceedsFifteenSeconds() {
        val caps = LipApi.parseCapabilities(JSONObject("""{"languages":[],"model":"real-model","max_duration_seconds":120}"""))
        assertEquals(15, caps.maxSeconds)
    }
    @Test fun rejectsInvalidCapabilities() {
        listOf("""{"languages":[],"model":"x","max_duration_seconds":0}""",
            """{"languages":[],"model":"","max_duration_seconds":15}""",
            """{"languages":[{"code":"en","label":"English","available":true},{"code":"en","label":"English","available":true}],"model":"x","max_duration_seconds":15}""").forEach { value ->
            assertThrows(IllegalArgumentException::class.java) { LipApi.parseCapabilities(JSONObject(value)) }
        }
    }
}
