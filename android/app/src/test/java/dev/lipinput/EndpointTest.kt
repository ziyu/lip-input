package dev.lipinput

import org.junit.Assert.*
import org.junit.Test

class EndpointTest {
    @Test fun acceptsHttpsAndPathPrefix() {
        assertEquals("https://example.com/prefix/v1/capabilities", Endpoint.parse(" https://EXAMPLE.com/prefix/ ").route("capabilities"))
        assertEquals("https://example.com:8443/v1/transcriptions", Endpoint.parse("https://example.com:8443").route("transcriptions"))
    }
    @Test fun rejectsUnsafeOrAmbiguousEndpoints() {
        listOf("http://example.com", "https://u:p@example.com", "https://example.com?x=y", "https://example.com/#x",
            "https://example.com:0", "https://example.com:65536", "https://", "https://example.com/a/../b",
            "https://example.com/a%2fb", "https://example.com/a b", "https://example.com\\evil", "file:///tmp/server",
            "https://example.com/a//b", "https://example.com/#", "https://example.com/?").forEach { input ->
            assertThrows(input, IllegalArgumentException::class.java) { Endpoint.parse(input) }
        }
    }
}
