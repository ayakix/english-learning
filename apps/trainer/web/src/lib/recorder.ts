// マイク録音 → 16kHz モノラル WAV
// Gemini に音声をそのまま渡すため、ブラウザ依存の WebM ではなく WAV にしている。
// 16kHz に落とすのは、音声認識には十分でアップロードが軽くなるため。

const TARGET_RATE = 16000;

// 録音したサンプルをメインスレッドに送るだけの AudioWorklet
const WORKLET = `class R extends AudioWorkletProcessor{process(i){const c=i[0]&&i[0][0];if(c)this.port.postMessage(c.slice(0));return true}}registerProcessor('rec',R)`;

export type RecOwner = "desc" | "shadow" | "test" | "pending" | null;

class Recorder {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  private analyser: AnalyserNode | null = null;
  private src: MediaStreamAudioSourceNode | null = null;
  private chunks: Float32Array[] = [];
  private echo: boolean | null = null;
  private t0 = 0;
  private buf = new Float32Array(1024);
  on = false;
  // どの機能が録音中か（説明の録音とシャドーイング録音が同時に動かないようにする）
  owner: RecOwner = null;

  // await をまたいで所有者が変わることを TypeScript は追えないので、比較はメソッド経由で行う
  isOwner(o: RecOwner): boolean {
    return this.owner === o;
  }

  async init(echo: boolean) {
    if (this.ctx && this.echo === echo) {
      if (this.ctx.state === "suspended") await this.ctx.resume();
      return;
    }
    // エコー除去の設定はストリーム取得時にしか指定できないので、変わったら取り直す
    this.stream?.getTracks().forEach((t) => t.stop());
    this.echo = echo;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: echo, noiseSuppression: echo, autoGainControl: true, channelCount: 1 },
    });
    if (!this.ctx) {
      this.ctx = new AudioContext();
      await this.ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" })));
      this.node = new AudioWorkletNode(this.ctx, "rec");
      this.node.port.onmessage = (e) => {
        if (this.on) this.chunks.push(e.data);
      };
      // Worklet を動かし続けるには destination につなぐ必要があるが、マイクの音は鳴らさない
      const mute = this.ctx.createGain();
      mute.gain.value = 0;
      this.node.connect(mute).connect(this.ctx.destination);
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 1024;
    }
    this.src?.disconnect();
    this.src = this.ctx.createMediaStreamSource(this.stream);
    this.src.connect(this.node!);
    this.src.connect(this.analyser!);
    if (this.ctx.state === "suspended") await this.ctx.resume();
  }

  async start(echo: boolean, owner: RecOwner) {
    await this.init(echo);
    this.chunks = [];
    this.on = true;
    this.owner = owner;
    this.t0 = performance.now();
  }

  /** 0〜1 の音量（メーター表示用） */
  level(): number {
    if (!this.on || !this.analyser) return 0;
    this.analyser.getFloatTimeDomainData(this.buf);
    let m = 0;
    for (const v of this.buf) m = Math.max(m, Math.abs(v));
    return Math.min(1, m * 1.6);
  }

  elapsed(): number {
    return this.on ? (performance.now() - this.t0) / 1000 : 0;
  }

  stop(): { blob: Blob; seconds: number } {
    this.on = false;
    this.owner = null;
    const sr = this.ctx!.sampleRate;
    let len = 0;
    for (const c of this.chunks) len += c.length;
    const all = new Float32Array(len);
    let o = 0;
    for (const c of this.chunks) {
      all.set(c, o);
      o += c.length;
    }
    // 区間平均で間引く（簡易的なローパスを兼ねる）
    const ratio = sr / TARGET_RATE;
    const outLen = Math.floor(len / ratio);
    const out = new Int16Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const a = Math.floor(i * ratio);
      const b = Math.min(len, Math.floor((i + 1) * ratio));
      let s = 0;
      for (let j = a; j < b; j++) s += all[j];
      const v = Math.max(-1, Math.min(1, s / Math.max(1, b - a)));
      out[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
    }
    return { blob: new Blob([wavHeader(out.length), out.buffer], { type: "audio/wav" }), seconds: outLen / TARGET_RATE };
  }

  /** リピート録音の「どうぞ」の合図 */
  beep() {
    if (!this.ctx) return;
    const o = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    o.frequency.value = 880;
    g.gain.value = 0.08;
    o.connect(g).connect(this.ctx.destination);
    o.start();
    o.stop(this.ctx.currentTime + 0.12);
  }
}

function wavHeader(samples: number): ArrayBuffer {
  const h = new DataView(new ArrayBuffer(44));
  const w = (p: number, s: string) => {
    for (let i = 0; i < s.length; i++) h.setUint8(p + i, s.charCodeAt(i));
  };
  w(0, "RIFF");
  h.setUint32(4, 36 + samples * 2, true);
  w(8, "WAVE");
  w(12, "fmt ");
  h.setUint32(16, 16, true);
  h.setUint16(20, 1, true);
  h.setUint16(22, 1, true);
  h.setUint32(24, TARGET_RATE, true);
  h.setUint32(28, TARGET_RATE * 2, true);
  h.setUint16(32, 2, true);
  h.setUint16(34, 16, true);
  w(36, "data");
  h.setUint32(40, samples * 2, true);
  return h.buffer;
}

// マイクと AudioContext は 1 つを使い回す（取り直すたびに許可ダイアログや遅延が出るため）
export const recorder = new Recorder();
