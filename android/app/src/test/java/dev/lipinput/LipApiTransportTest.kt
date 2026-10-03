package dev.lipinput

import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import java.io.File
import java.net.Proxy
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/** Test-only HTTPS server; no production code contains synthetic recognition results. */
class LipApiTransportTest {
    private lateinit var server: MockWebServer
    private lateinit var api: LipApi
    private lateinit var endpoint: Endpoint
    private lateinit var video: File

    @Before fun prepare() {
        val certificate = HeldCertificate.Builder().commonName("localhost").addSubjectAlternativeName("localhost").build()
        val serverTls = HandshakeCertificates.Builder().heldCertificate(certificate).build()
        val clientTls = HandshakeCertificates.Builder().addTrustedCertificate(certificate.certificate).build()
        server = MockWebServer().apply { useHttps(serverTls.sslSocketFactory(), false); start() }
        api = LipApi(OkHttpClient.Builder().proxy(Proxy.NO_PROXY)
            .sslSocketFactory(clientTls.sslSocketFactory(), clientTls.trustManager))
        endpoint = Endpoint.parse(server.url("/").toString())
        video = File.createTempFile("test-only-clip", ".mp4").apply { writeText("TEST FIXTURE, NOT REAL VIDEO") }
    }
    @After fun cleanup() {
        api.client.dispatcher.executorService.shutdown()
        api.client.connectionPool.evictAll()
        server.shutdown()
        video.delete()
    }
    private fun request(): Result<Transcript> {
        val done = CountDownLatch(1)
        val result = AtomicReference<Result<Transcript>>()
        api.transcribe(endpoint, video, "zh") { result.set(it); done.countDown() }
        assertTrue("Request did not finish", done.await(15, TimeUnit.SECONDS))
        return result.get()
    }
    @Test fun uploadsExpectedLanguageAndVideoOnce() {
        server.enqueue(MockResponse().setHeader("Content-Type", "application/json")
            .setBody("""{"text":"测试文本","language":"zh","model":"test-double"}"""))
        assertEquals("测试文本", request().getOrThrow().text)
        val received = server.takeRequest(1, TimeUnit.SECONDS)!!
        assertEquals("/v1/transcriptions", received.path)
        assertEquals("POST", received.method)
        val multipart = received.body.readUtf8()
        assertTrue(multipart.contains("name=\"language\""))
        assertTrue(multipart.contains("\r\nzh\r\n"))
        assertTrue(multipart.contains("name=\"video\"; filename=\"clip.mp4\""))
        assertEquals(1, server.requestCount)
    }
    @Test fun serviceUnavailableRetryAfterZeroNeverReplaysClip() {
        server.enqueue(MockResponse().setResponseCode(503).setHeader("Retry-After", "0")
            .setBody("""{"detail":{"code":"model_unavailable","message":"Model offline"}}"""))
        server.enqueue(MockResponse().setBody("""{"text":"unexpected replay","language":"zh","model":"test-double"}"""))
        assertEquals("Model offline", request().exceptionOrNull()?.message)
        assertEquals(1, server.requestCount)
    }
    @Test fun redirectNeverSendsClipToAnotherPath() {
        server.enqueue(MockResponse().setResponseCode(307).setHeader("Location", server.url("/other")))
        server.enqueue(MockResponse().setBody("""{"text":"unexpected redirect","language":"zh","model":"test-double"}"""))
        assertTrue(request().exceptionOrNull()?.message.orEmpty().contains("Redirect refused"))
        assertEquals(1, server.requestCount)
    }
    @Test fun malformedSuccessDoesNotProduceATranscript() {
        server.enqueue(MockResponse().setBody("""{"text":" ","language":"zh","model":"test-double"}"""))
        assertTrue(request().isFailure)
    }
}
