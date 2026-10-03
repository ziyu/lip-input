package dev.lipinput

import org.junit.Assert.*
import org.junit.Test

class CaptureFlowTest {
    @Test fun onlyReadyClipCanBeUploadedWithConsent() {
        val flow = CaptureFlow()
        assertFalse(flow.consentAndUpload(0))
        val id = flow.beginRecording()
        assertFalse(flow.consentAndUpload(id))
        assertTrue(flow.stopRecording(id))
        assertFalse(flow.consentAndUpload(id))
        assertTrue(flow.finishRecording(id))
        assertTrue(flow.consentAndUpload(id))
        assertFalse(flow.consentAndUpload(id))
        assertTrue(flow.uploadSucceeded(id))
        assertEquals(CaptureFlow.Phase.IDLE, flow.phase)
    }
    @Test fun staleRecordingCannotReviveCanceledClip() {
        val flow = CaptureFlow()
        val old = flow.beginRecording()
        flow.cancel()
        val new = flow.beginRecording()
        assertFalse(flow.finishRecording(old))
        assertFalse(flow.consentAndUpload(old))
        assertTrue(flow.finishRecording(new))
    }
    @Test fun failureReturnsToReadyAndNeedsNewConsent() {
        val flow = CaptureFlow()
        val id = flow.beginRecording()
        flow.finishRecording(id)
        flow.consentAndUpload(id)
        assertTrue(flow.uploadFailed(id))
        assertEquals(CaptureFlow.Phase.READY, flow.phase)
        assertFalse(flow.uploadSucceeded(id))
        assertTrue(flow.consentAndUpload(id))
    }
    @Test fun canceledUploadCannotReplaceNewTranscript() {
        val flow = CaptureFlow()
        val id = flow.beginRecording()
        flow.finishRecording(id)
        flow.consentAndUpload(id)
        flow.cancel()
        assertFalse(flow.uploadSucceeded(id))
        assertFalse(flow.uploadFailed(id))
        assertEquals(CaptureFlow.Phase.IDLE, flow.phase)
    }
    @Test fun requestGateDropsLateCallbacksAfterCancelOrRetry() {
        val gate = RequestGate()
        val first = gate.next()
        gate.invalidate()
        assertFalse(gate.accepts(first))
        val second = gate.next()
        assertFalse(gate.accepts(first))
        assertTrue(gate.accepts(second))
    }
}
