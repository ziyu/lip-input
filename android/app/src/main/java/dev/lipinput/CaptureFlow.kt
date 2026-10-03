package dev.lipinput

/** Main-thread state machine. Every async callback must carry its original generation. */
class CaptureFlow {
    enum class Phase { IDLE, RECORDING, FINALIZING, READY, UPLOADING }
    var phase = Phase.IDLE
        private set
    var generation = 0L
        private set

    fun beginRecording(): Long {
        check(phase == Phase.IDLE)
        generation++
        phase = Phase.RECORDING
        return generation
    }
    fun stopRecording(id: Long): Boolean = transition(id, Phase.RECORDING, Phase.FINALIZING)
    fun finishRecording(id: Long): Boolean {
        if (id != generation || phase !in setOf(Phase.RECORDING, Phase.FINALIZING)) return false
        phase = Phase.READY
        return true
    }
    /** Called only from the positive button of the per-clip upload confirmation. */
    fun consentAndUpload(id: Long): Boolean = transition(id, Phase.READY, Phase.UPLOADING)
    fun uploadFailed(id: Long): Boolean = transition(id, Phase.UPLOADING, Phase.READY)
    fun uploadSucceeded(id: Long): Boolean = transition(id, Phase.UPLOADING, Phase.IDLE)
    fun cancel() { generation++; phase = Phase.IDLE }
    private fun transition(id: Long, from: Phase, to: Phase): Boolean {
        if (id != generation || phase != from) return false
        phase = to
        return true
    }
}

class RequestGate {
    private var current = 0L
    fun next(): Long = ++current
    fun accepts(token: Long): Boolean = token == current
    fun invalidate() { current++ }
}
