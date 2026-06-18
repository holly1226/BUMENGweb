/**
 * useSound — TRPG 音效系统
 * 使用 Web Audio API 合成音效，无需外部音频文件
 * 提供：背景氛围音（地牢/奇幻风格）+ 按钮点击音效
 */

// 延迟初始化，避免在 Node.js 构建环境报错
let AUDIO_CTX = null;

function getAudioCtx() {
  if (!AUDIO_CTX) {
    AUDIO_CTX = new (window.AudioContext || window.webkitAudioContext)();
  }
  return AUDIO_CTX;
}

// 主增益节点（总音量控制）
let masterGain = null;
let bgmNode = null;        // 当前背景音节点
let bgmGain = null;        // 背景音增益
let isBgmPlaying = false;
let bgmType = null;        // 当前背景音类型

// 预创建音频上下文（用户首次交互后激活）
let unlocked = false;

export function unlockAudio() {
  if (unlocked) return;
  const ctx = getAudioCtx();
  if (ctx.state === 'suspended') {
    ctx.resume().then(() => {
      unlocked = true;
    }).catch(() => {});
  } else {
    unlocked = true;
  }

  // 同时解锁 HTML5 Audio（TTS 语音播放需要）
  // 浏览器自动播放策略要求 Audio 也必须在用户手势中首次激活
  try {
    const silentAudio = new Audio("data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA");
    silentAudio.volume = 0;
    silentAudio.play().then(() => {
      silentAudio.pause();
      silentAudio.remove();
    }).catch(() => {});
  } catch (e) {
    // 静默忽略
  }
}

// ===================== 按钮音效 =====================

/**
 * 播放按钮点击音效
 * @param {'click'|'confirm'|'cancel'|'option'|'dice'|'success'} type
 */
export function playButtonSound(type = 'click') {
  unlockAudio();
  const ctx = getAudioCtx();
  if (ctx.state !== 'running') return;

  const now = ctx.currentTime;
  const gain = ctx.createGain();
  gain.connect(ctx.destination);

  switch (type) {
    case 'confirm': {
      // 确认音：短促上升双音 (叮~)
      gain.gain.setValueAtTime(0.15, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);

      const osc1 = ctx.createOscillator();
      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(800, now);
      osc1.frequency.exponentialRampToValueAtTime(1200, now + 0.08);
      osc1.connect(gain);
      osc1.start(now);
      osc1.stop(now + 0.12);

      const osc2 = ctx.createOscillator();
      osc2.type = 'sine';
      osc2.frequency.setValueAtTime(1200, now + 0.08);
      osc2.frequency.exponentialRampToValueAtTime(1600, now + 0.16);
      osc2.connect(gain);
      osc2.start(now + 0.08);
      osc2.stop(now + 0.3);
      break;
    }

    case 'cancel': {
      // 取消/返回音：低沉下降 (咚)
      gain.gain.setValueAtTime(0.12, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);

      const osc = ctx.createOscillator();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(400, now);
      osc.frequency.exponentialRampToValueAtTime(200, now + 0.15);
      osc.connect(gain);
      osc.start(now);
      osc.stop(now + 0.2);
      break;
    }

    case 'option': {
      // 选项选择音：轻快的拨弦声 (咔~)
      gain.gain.setValueAtTime(0.1, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);

      const osc = ctx.createOscillator();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(1000, now);
      osc.frequency.exponentialRampToValueAtTime(600, now + 0.08);
      osc.connect(gain);
      osc.start(now);
      osc.stop(now + 0.1);

      // 添加一点噪声模拟拨弦
      const noiseGain = ctx.createGain();
      noiseGain.gain.setValueAtTime(0.04, now);
      noiseGain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
      noiseGain.connect(ctx.destination);
      const bufferSize = ctx.sampleRate * 0.05;
      const noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
      const data = noiseBuffer.getChannelData(0);
      for (let i = 0; i < bufferSize; i++) data[i] = Math.random() * 2 - 1;
      const noise = ctx.createBufferSource();
      noise.buffer = noiseBuffer;
      noise.connect(noiseGain);
      noise.start(now);
      noise.stop(now + 0.05);
      break;
    }

    case 'dice': {
      // 骰子音：连续的咔嗒声 (嗒嗒嗒嗒~)
      gain.gain.setValueAtTime(0.08, now);
      for (let i = 0; i < 6; i++) {
        const t = now + i * 0.06;
        gain.gain.setValueAtTime(0.08 * (1 - i * 0.12), t);
        const osc = ctx.createOscillator();
        osc.type = 'square';
        osc.frequency.setValueAtTime(200 + Math.random() * 600, t);
        osc.connect(gain);
        osc.start(t);
        osc.stop(t + 0.03);
      }
      gain.gain.setValueAtTime(0.001, now + 0.4);
      break;
    }

    case 'success': {
      // 成功音：明亮三连音 (叮叮当~)
      gain.gain.setValueAtTime(0.12, now);
      const notes = [523, 659, 784]; // C5, E5, G5
      notes.forEach((freq, i) => {
        const t = now + i * 0.1;
        const osc = ctx.createOscillator();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, t);
        osc.connect(gain);
        osc.start(t);
        osc.stop(t + 0.15);
      });
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.5);
      break;
    }

    default: // 'click' — 通用点击音：短促清脆
    case 'click': {
      gain.gain.setValueAtTime(0.08, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);

      const osc = ctx.createOscillator();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(1200, now);
      osc.frequency.exponentialRampToValueAtTime(800, now + 0.05);
      osc.connect(gain);
      osc.start(now);
      osc.stop(now + 0.08);
      break;
    }
  }
}

// ===================== 键盘打字音效 =====================

let lastTypingSound = 0; // 节流：防止快速连续打字时声音重叠

/**
 * 播放键盘打字音效 — 短促柔和按键声，营造沉浸感
 * 每 80ms 最多触发一次（防止快速打字时声音重叠刺耳）
 */
export function playTypingSound() {
  const now = performance.now();
  if (now - lastTypingSound < 80) return; // 节流
  lastTypingSound = now;

  unlockAudio();
  const ctx = getAudioCtx();
  if (ctx.state !== 'running') return;

  const t = ctx.currentTime;
  const gain = ctx.createGain();
  gain.gain.setValueAtTime(0.03, t);
  gain.gain.exponentialRampToValueAtTime(0.001, t + 0.05);
  gain.connect(ctx.destination);

  // 产生类似老式打字机风格的“嗒”声
  const osc = ctx.createOscillator();
  osc.type = 'triangle';
  osc.frequency.setValueAtTime(200 + Math.random() * 200, t); // 每次频率随机微调，模拟自然打键
  osc.connect(gain);
  osc.start(t);
  osc.stop(t + 0.04);

  // 添加极短噪声模拟按键摩擦
  const noiseGain = ctx.createGain();
  noiseGain.gain.setValueAtTime(0.015, t);
  noiseGain.gain.exponentialRampToValueAtTime(0.001, t + 0.03);
  noiseGain.connect(ctx.destination);
  const bufferSize = ctx.sampleRate * 0.03;
  const noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
  const data = noiseBuffer.getChannelData(0);
  for (let i = 0; i < bufferSize; i++) data[i] = Math.random() * 2 - 1;
  const noise = ctx.createBufferSource();
  noise.buffer = noiseBuffer;
  noise.connect(noiseGain);
  noise.start(t);
  noise.stop(t + 0.03);
}

// ===================== 背景音乐 =====================

/** 停止当前背景音 */
export function stopBgm() {
  if (bgmGain) {
    try {
      const ctx = getAudioCtx();
      bgmGain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.5);
      setTimeout(() => {
        if (bgmNode) {
          try { bgmNode.stop(); } catch (e) { /* ignore */ }
          bgmNode = null;
        }
        if (bgmGain) {
          bgmGain.disconnect();
          bgmGain = null;
        }
      }, 600);
    } catch (e) {
      if (bgmNode) {
        try { bgmNode.stop(); } catch (e2) { /* ignore */ }
        bgmNode = null;
      }
      if (bgmGain) {
        bgmGain.disconnect();
        bgmGain = null;
      }
    }
  } else {
    if (bgmNode) {
      try { bgmNode.stop(); } catch (e) { /* ignore */ }
      bgmNode = null;
    }
  }
  isBgmPlaying = false;
  bgmType = null;
}

/**
 * 播放/切换背景氛围音（带淡入淡出过渡）
 * @param {'lobby'|'explore'|'combat'|'mystery'|'peaceful'|'tense'|'none'} scene
 * @param {number} volume 音量 0-1，默认 0.08
 */
export function playBgm(scene = 'lobby', volume = 0.08) {
  unlockAudio();
  const ctx = getAudioCtx();
  if (ctx.state !== 'running') return;

  // 如果已经是同类型，不重复播放
  if (isBgmPlaying && bgmType === scene) return;

  // 淡出旧BGM
  stopBgm();

  if (scene === 'none') return;

  bgmType = scene;

  // 创建增益节点（淡入效果）
  bgmGain = ctx.createGain();
  bgmGain.gain.setValueAtTime(0, ctx.currentTime);
  bgmGain.gain.linearRampToValueAtTime(volume, ctx.currentTime + 0.8);
  bgmGain.connect(ctx.destination);

  switch (scene) {
    case 'lobby': {
      // 大厅：柔和温暖的持续和声
      playAmbientDrone([130.8, 164.8, 196.0], 'sine', 0.06, bgmGain); // C3, E3, G3
      break;
    }

    case 'explore': {
      // 探索：神秘氛围，低频长音 + 随机高音点缀
      playAmbientDrone([110.0, 138.6, 165.0], 'sine', 0.05, bgmGain); // A2, C#3, E3
      // 随机高音点缀
      scheduleRandomPings(bgmGain, 0.03, [330, 440, 550], 3, 8);
      break;
    }

    case 'combat': {
      // 战斗：紧张的低频脉冲
      playAmbientDrone([98.0, 130.8], 'sawtooth', 0.04, bgmGain); // G2, C3
      // 心跳般的低频鼓点
      scheduleHeartbeat(bgmGain, 0.06);
      break;
    }

    case 'mystery': {
      // 悬疑：不协和音程 + 风声感
      playAmbientDrone([138.6, 207.7], 'triangle', 0.04, bgmGain); // C#3, G#3
      // 风声
      playWindNoise(bgmGain, 0.03);
      break;
    }

    case 'peaceful': {
      // 宁静：悠扬的五声音阶
      playAmbientDrone([196.0, 246.9, 293.7], 'sine', 0.05, bgmGain); // G3, B3, D4
      scheduleRandomPings(bgmGain, 0.02, [392, 440, 523, 587], 5, 12);
      break;
    }

    case 'tense': {
      // 紧张：低音脉冲 + 不和谐泛音
      playAmbientDrone([82.4, 110.0], 'sawtooth', 0.04, bgmGain); // E2, A2
      scheduleHeartbeat(bgmGain, 0.08);
      break;
    }

    default:
      playAmbientDrone([130.8, 196.0], 'sine', 0.05, bgmGain);
      break;
  }

  isBgmPlaying = true;
}

// ===================== 内部合成函数 =====================

/** 持续氛围音（长音 drone） */
function playAmbientDrone(frequencies, waveType, gainLevel, outputNode) {
  const ctx = getAudioCtx();
  const now = ctx.currentTime;
  const duration = 60; // 每60秒重新生成以保持循环

  frequencies.forEach((freq) => {
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(gainLevel, now + 1.5); // 淡入
    gain.connect(outputNode);

    const osc = ctx.createOscillator();
    osc.type = waveType;
    osc.frequency.setValueAtTime(freq, now);
    // 微小的频率漂移制造氛围感
    osc.frequency.linearRampToValueAtTime(freq * 1.005, now + 30);
    osc.frequency.linearRampToValueAtTime(freq * 0.995, now + 60);
    osc.connect(gain);
    osc.start(now);
    osc.stop(now + duration + 1);

    bgmNode = osc; // 保存引用以便停止
  });
}

/** 随机高音点缀 */
function scheduleRandomPings(outputNode, gainLevel, frequencies, minInterval, maxInterval) {
  const scheduleNext = () => {
    if (!isBgmPlaying || bgmType === null) return;

    const ctx = getAudioCtx();
    const now = ctx.currentTime;
    const delay = minInterval + Math.random() * (maxInterval - minInterval);
    const freq = frequencies[Math.floor(Math.random() * frequencies.length)];

    const gain = ctx.createGain();
    gain.gain.setValueAtTime(gainLevel, now + delay);
    gain.gain.exponentialRampToValueAtTime(0.001, now + delay + 1.5);
    gain.connect(outputNode);

    const osc = ctx.createOscillator();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(freq, now + delay);
    osc.connect(gain);
    osc.start(now + delay);
    osc.stop(now + delay + 1.5);

    setTimeout(scheduleNext, delay * 1000 + 100);
  };
  scheduleNext();
}

/** 心跳节奏 */
function scheduleHeartbeat(outputNode, gainLevel) {
  const scheduleBeat = () => {
    if (!isBgmPlaying || bgmType === null) return;

    const ctx = getAudioCtx();
    const now = ctx.currentTime;
    const interval = 1.2; // 心跳间隔

    // 两声短促的低音
    [0, 0.15].forEach((offset) => {
      const gain = ctx.createGain();
      gain.gain.setValueAtTime(gainLevel, now + offset);
      gain.gain.exponentialRampToValueAtTime(0.001, now + offset + 0.25);
      gain.connect(outputNode);

      const osc = ctx.createOscillator();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(55, now + offset); // 低频
      osc.connect(gain);
      osc.start(now + offset);
      osc.stop(now + offset + 0.25);
    });

    setTimeout(scheduleBeat, interval * 1000);
  };
  scheduleBeat();
}

/** 风声噪声 */
function playWindNoise(outputNode, gainLevel) {
  const ctx = getAudioCtx();
  const bufferSize = ctx.sampleRate * 4;
  const noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
  const data = noiseBuffer.getChannelData(0);

  // 有色噪声（偏低频）
  let lastOut = 0;
  for (let i = 0; i < bufferSize; i++) {
    const white = Math.random() * 2 - 1;
    lastOut = lastOut + 0.02 * (white - lastOut);
    data[i] = lastOut * 0.5;
  }

  const gain = ctx.createGain();
  gain.gain.setValueAtTime(gainLevel * 0.5, ctx.currentTime);
  gain.gain.linearRampToValueAtTime(gainLevel, ctx.currentTime + 1);
  gain.connect(outputNode);

  const noise = ctx.createBufferSource();
  noise.buffer = noiseBuffer;
  noise.loop = true;
  noise.connect(gain);
  noise.start();
}

// ===================== 场景名称映射到背景音类型 =====================

/**
 * 根据场景名称推荐背景音类型
 * @param {string} sceneName
 * @returns {'lobby'|'explore'|'combat'|'mystery'|'peaceful'|'tense'}
 */
export function getSceneBgmType(sceneName) {
  const name = (sceneName || '').toLowerCase();

  if (/战斗|战|敌|怪|boss|袭击|攻|杀|决斗|对抗/.test(name)) return 'combat';
  if (/森林|探索|旅|行|路|荒野|洞|地牢|遗迹|迷宫|冒险|前进/.test(name)) return 'explore';
  if (/神秘|秘密|谜|暗|影|鬼|幽灵|诅咒|诡异|悬疑/.test(name)) return 'mystery';
  if (/村庄|城镇|酒馆|家|营火|休息|安全|和平|宁静|治愈|温暖/.test(name)) return 'peaceful';
  if (/紧张|危险|逃|陷阱|追逐|紧迫/.test(name)) return 'tense';

  // 默认大厅
  return 'lobby';
}
