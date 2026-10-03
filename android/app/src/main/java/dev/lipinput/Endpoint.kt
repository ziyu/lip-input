package dev.lipinput

import java.net.URI

/** A verified server base URL, optionally with a simple path prefix. */
class Endpoint private constructor(val base: String) {
    fun route(path: String): String {
        require(path == "capabilities" || path == "transcriptions")
        return "$base/v1/$path"
    }
    companion object {
        fun parse(raw: String): Endpoint {
            val value = raw.trim()
            require(value.isNotEmpty() && value.none { it.isWhitespace() || it.isISOControl() }) {
                "Enter an HTTPS server URL"
            }
            val uri = try { URI(value) } catch (_: Exception) {
                throw IllegalArgumentException("Enter a valid HTTPS server URL")
            }
            require(uri.scheme?.lowercase() == "https" && !uri.host.isNullOrBlank()) {
                "Use an HTTPS URL with a hostname"
            }
            require(uri.rawUserInfo == null && uri.rawQuery == null && uri.rawFragment == null) {
                "The server URL must not include credentials, a query, or a fragment"
            }
            require(uri.port == -1 || uri.port in 1..65535) { "Invalid server port" }
            val path = uri.rawPath.orEmpty().trimEnd('/')
            require(path.isEmpty() || path.matches(Regex("(?:/[A-Za-z0-9._~-]+)+"))) {
                "Use a simple server path without escaped characters"
            }
            require(path.split('/').none { it == "." || it == ".." }) { "Invalid server path" }
            // URI validation rejects backslashes and malformed authorities before any network request.
            val authority = uri.rawAuthority.lowercase()
            return Endpoint("https://$authority$path")
        }
    }
}
