import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
// socket.io 通过 CDN 加载（index.html），使用全局 io
const getIO = () => window.io;

// 音效系统
import { unlockAudio, playButtonSound, playBgm, stopBgm, getSceneBgmType, playTypingSound } from './useSound.js';

// 结局卡片导出（懒加载，仅在需要时导入）
let html2canvasModule = null;
const getHtml2canvas = async () => {
  if (!html2canvasModule) {
    html2canvasModule = await import('html2canvas');
  }
  return html2canvasModule.default;
};

const backendUrl = import.meta.env.VITE_BACKEND_URL || undefined;

/* 统一分隔符处理：/n \n \\n 都视为换行 */
const SPLIT_RE = /\n|\\n|\/n/;

/* 解析消息中的选项：→ xxx / - xxx */
function parseOptions(text) {
  if (!text) return [];
  const lines = text.split(SPLIT_RE);
  return lines
    .map((l) => l.trim())
    .filter((l) => /^[→\-–—>]\s/.test(l))
    .map((l) => l.replace(/^[→\-–—>]\s*/, '').trim());
}

/* 移除选项行，只保留正文 */
function stripOptions(text) {
  if (!text) return '';
  return text
    .split(SPLIT_RE)
    .filter((l) => !/^[→\-–—>]\s/.test(l.trim()))
    .join('\n')
    .trim();
}

/* 清理 Markdown 标记 */
function cleanMarkdown(text) {
  if (!text) return '';
  return text
    .replace(/\*{1,2}([^*]+)\*{1,2}/g, '$1')
    .replace(/#{1,4}\s*/g, '')
    .replace(/`([^`]+)`/g, '$1')
    .trim();
}

/* 解析私密情报：按标题和分段拆分 */
function parsePrivateMessage(content) {
  if (!content) return { title: '', sections: [] };
  const cleaned = cleanMarkdown(content);
  const titleMatch = cleaned.match(/^(.+?)\n/);
  let title = '';
  let body = cleaned;
  if (titleMatch && titleMatch[1].length < 30) {
    title = titleMatch[1].replace(/[【】\[\]]/g, '').trim();
    body = cleaned.slice(titleMatch[0].length);
  }
  const sections = [];
  const lines = body.split(/\n/).filter((l) => l.trim());
  for (const line of lines) {
    const trimmed = line.trim();
    const kv = trimmed.match(/^(.{1,12})[：:]\s*(.+)/);
    const bullet = trimmed.match(/^[-•🔹🔸▸]\s*(.+)/);
    if (kv) {
      const label = kv[1].replace(/[【】\[\]🔹🔸▸]/g, '').trim();
      sections.push({ label, text: kv[2].trim() });
    } else if (bullet) {
      sections.push({ label: '', text: bullet[1].trim() });
    } else {
      sections.push({ label: '', text: trimmed });
    }
  }
  return { title, sections };
}

/* ---------- 粒子背景组件 ---------- */
function ParticleBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let animId;
    let particles = [];

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    // 创建粒子（减少数量，降低渲染负担）
    const count = 30;
    for (let i = 0; i < count; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        r: Math.random() * 1.5 + 0.3,
        vx: (Math.random() - 0.5) * 0.25,
        vy: (Math.random() - 0.5) * 0.25,
        alpha: Math.random() * 0.4 + 0.15,
        twinkle: Math.random() * Math.PI * 2,
        twinkleSpeed: Math.random() * 0.015 + 0.005,
      });
    }

    let frameCount = 0;
    const animate = () => {
      frameCount++;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles.forEach((p) => {
        p.x += p.vx;
        p.y += p.vy;
        p.twinkle += p.twinkleSpeed;

        if (p.x < 0) p.x = canvas.width;
        if (p.x > canvas.width) p.x = 0;
        if (p.y < 0) p.y = canvas.height;
        if (p.y > canvas.height) p.y = 0;

        const alpha = p.alpha + Math.sin(p.twinkle) * 0.12;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(147, 197, 253, ${Math.max(0.05, alpha)})`;
        ctx.fill();
      });

      // 连线（每3帧执行一次，降低计算量）
      if (frameCount % 3 === 0) {
        for (let i = 0; i < particles.length; i++) {
          for (let j = i + 1; j < particles.length; j++) {
            const dx = particles[i].x - particles[j].x;
            const dy = particles[i].y - particles[j].y;
            const dist = dx * dx + dy * dy; // 避免 sqrt
            if (dist < 120 * 120) {
              ctx.beginPath();
              ctx.moveTo(particles[i].x, particles[i].y);
              ctx.lineTo(particles[j].x, particles[j].y);
              ctx.strokeStyle = `rgba(147, 197, 253, ${0.05 * (1 - Math.sqrt(dist) / 120)})`;
              ctx.lineWidth = 0.5;
              ctx.stroke();
            }
          }
        }
      }

      animId = requestAnimationFrame(animate);
    };
    animate();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return <canvas ref={canvasRef} className="fixed inset-0 z-0 pointer-events-none" />;
}

/* ---------- 光标闪烁打字效果（React.memo 优化） ---------- */
const TypewriterText = React.memo(function TypewriterText({ text, speed = 60, className = '' }) {
  const [displayed, setDisplayed] = useState('');
  const cursorRef = useRef(null);
  const [cursorVisible, setCursorVisible] = useState(true);

  useEffect(() => {
    if (!text) return;
    setDisplayed('');
    let i = 0;
    const timer = setInterval(() => {
      i++;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) clearInterval(timer);
    }, speed);
    return () => clearInterval(timer);
  }, [text, speed]);

  // 光标闪烁用 CSS animation，避免 JS setInterval
  useEffect(() => {
    if (cursorRef.current) {
      cursorRef.current.style.animation = 'blink 0.53s step-end infinite';
    }
  }, []);

  return (
    <span className={className}>
      {displayed}
      <span ref={cursorRef} className="inline-block w-[2px] h-[1em] bg-blue-300 align-middle ml-0.5">▏</span>
    </span>
  );
});

/* ========== 主应用组件 ========== */
export default function App() {
  const socket = useMemo(() => {
    const ioFn = getIO();
    const s = ioFn(backendUrl, {
      autoConnect: false,
      transports: ['websocket', 'polling'],
    });
    return s;
  }, []);
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [inventory, setInventory] = useState([]);
  const [scene, setScene] = useState({ name: '等待开场', description: '请创建或加入一个网页房间。' });
  const [playerCard, setPlayerCard] = useState(null);
  const [privateMessages, setPrivateMessages] = useState([]);
  const [backgroundImage, setBackgroundImage] = useState('/灵感收集大厅.png');
  const [userName, setUserName] = useState(() => localStorage.getItem('trpg_username') || '');
  const [roomNumberInput, setRoomNumberInput] = useState('');
  const [roomInfo, setRoomInfo] = useState(null);
  const [players, setPlayers] = useState([]);
  const [stage, setStage] = useState('IDLE');
  const [worldviewPref, setWorldviewPref] = useState('');
  const [rolePref, setRolePref] = useState('');
  const [totalRounds, setTotalRounds] = useState(15);
  const [suggestions, setSuggestions] = useState([]);
  const [rolePrefs, setRolePrefs] = useState({});
  const [dmStatus, setDmStatus] = useState('');
  const [joinError, setJoinError] = useState('');
  const [connected, setConnected] = useState(socket.connected);
  // 响应式：手机端默认收起左侧面板，PC/iPad保持展开
  const isMobileDevice = () => typeof window !== 'undefined' && window.innerWidth < 768;
  const [isMobile, setIsMobile] = useState(isMobileDevice);
  const [showLeftPanel, setShowLeftPanel] = useState(!isMobileDevice());
  const [showRightPanel, setShowRightPanel] = useState(false); // 默认收起
  const [roomOwner, setRoomOwner] = useState(''); // 当前房主名
  const [diceResult, setDiceResult] = useState(null);
  const [waitingPhase, setWaitingPhase] = useState(false); // 等待动效阶段
  const [selectedOptionIndex, setSelectedOptionIndex] = useState(null); // 已选中的DM选项
  const [optionGenerating, setOptionGenerating] = useState(false); // 选中后生成中
  const [playerAvatarUrl, setPlayerAvatarUrl] = useState(''); // 玩家角色头像URL
  const [showAvatarModal, setShowAvatarModal] = useState(false); // 头像放大弹窗
  const [currentRound, setCurrentRound] = useState(0); // 当前回合数
  const [isFinalRound, setIsFinalRound] = useState(false); // 是否为最终回合
  const [showRoundBanner, setShowRoundBanner] = useState(false); // 回合切换横幅
  const [prevBgImage, setPrevBgImage] = useState(''); // 上一张背景图（用于淡出过渡）
  const [bgTransitioning, setBgTransitioning] = useState(false); // 背景图切换中
  const [selfIntroActive, setSelfIntroActive] = useState(false); // 是否在自我介绍环节
  const [selfIntroDone, setSelfIntroDone] = useState(false); // 当前玩家是否已完成自我介绍
  const [gameEnding, setGameEnding] = useState(null); // 结局卡片数据
  const [showEndingCard, setShowEndingCard] = useState(false); // 是否展示结局卡片弹窗

  // 预设场景背景图（CSS渐变风格，用于DM消息轮换）
  const SCENE_BACKGROUNDS = useMemo(() => [
    'linear-gradient(135deg, #1a1a2e 0%, #16213e 40%, #0f3460 100%)',
    'linear-gradient(135deg, #1a1a2e 0%, #2d1b69 40%, #0f3460 100%)',
    'linear-gradient(135deg, #0d1b2a 0%, #1b2838 40%, #1a3a5c 100%)',
    'linear-gradient(135deg, #1a1a2e 0%, #3d1e3d 40%, #1a1a3e 100%)',
    'linear-gradient(135deg, #0a1628 0%, #1a2a4a 40%, #0d2137 100%)',
    'linear-gradient(135deg, #1a1a2e 0%, #1e3a5f 40%, #2a1a4a 100%)',
    'linear-gradient(135deg, #111d2e 0%, #1b2d4a 40%, #1a1040 100%)',
    'linear-gradient(135deg, #1a1a2e 0%, #2a1a3e 40%, #0f2a4a 100%)',
  ], []);
  const [sceneBgIndex, setSceneBgIndex] = useState(0); // 当前场景背景索引
  const [dmMessageCount, setDmMessageCount] = useState(0); // DM消息计数（用于轮换背景）

  // 开场页状态
  const [appPhase, setAppPhase] = useState('title'); // title | nameInput | roomSelect | inGame
  const [nameInputValue, setNameInputValue] = useState('');
  const [roomMode, setRoomMode] = useState(null); // 'create' | 'join'
  const [joinRoomInput, setJoinRoomInput] = useState('');
  const [titleVisible, setTitleVisible] = useState(false);
  const [creatingRoom, setCreatingRoom] = useState(false); // loading 状态

  const messagesEndRef = useRef(null);
  const chatEndRef = useRef(null);
  const optionTimeoutRef = useRef(null); // 选项锁定超时保护

  // TTS 音频播放队列（必须在组件顶层声明）
  const audioQueueRef = useRef([]);
  const isPlayingRef = useRef(false);
  const currentAudioRef = useRef(null);

  const clearTtsQueue = useCallback(() => {
    // 如果音频刚被 resume（从浏览器阻止状态恢复），不要打断它
    // 只清空待播放队列，让当前正在播放的音频自然结束
    if (ttsJustResumedRef.current) {
      audioQueueRef.current = [];
      return;
    }
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }
    audioQueueRef.current = [];
    isPlayingRef.current = false;
  }, []);

  // 当浏览器阻止自动播放时，等待下一次用户点击后重试
  const ttsBlockedRef = useRef(false);
  const ttsJustResumedRef = useRef(false); // 防止 resume 后立即被 clearTtsQueue 打断
  const playNextAudioRef = useRef(null);
  
  const playNextAudio = useCallback(() => {
    if (isPlayingRef.current || audioQueueRef.current.length === 0) return;
    isPlayingRef.current = true;
    const next = audioQueueRef.current.shift();
    const audio = new Audio(`data:audio/mp3;base64,${next.audio}`);
    currentAudioRef.current = audio;
    audio.onended = () => {
      currentAudioRef.current = null;
      isPlayingRef.current = false;
      playNextAudio();
    };
    audio.onerror = (e) => {
      console.warn('TTS 音频播放失败', e);
      currentAudioRef.current = null;
      isPlayingRef.current = false;
      playNextAudio();
    };
    audio.play().catch((err) => {
      if (err.name === 'NotAllowedError') {
        console.warn('🔇 浏览器阻止了自动播放，等待用户点击后恢复...');
        // 把音频放回队列头部，等用户点击后重试
        audioQueueRef.current.unshift(next);
        ttsBlockedRef.current = true;
      } else {
        console.warn('TTS 播放异常:', err.message);
      }
      currentAudioRef.current = null;
      isPlayingRef.current = false;
      // 不要调用 playNextAudio，等待用户交互
    });
  }, []);

  // 保存 playNextAudio 引用供全局事件使用
  playNextAudioRef.current = playNextAudio;
  
  const resumeTtsOnClick = useCallback(() => {
    if (ttsBlockedRef.current) {
      ttsBlockedRef.current = false;
      ttsJustResumedRef.current = true;
      console.log('🔊 用户已交互，恢复TTS播放');
      playNextAudioRef.current?.();
      // 500ms 后允许正常的 clearTtsQueue
      setTimeout(() => { ttsJustResumedRef.current = false; }, 500);
    }
  }, []);

  // 响应式窗口大小监听
  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const inRoom = Boolean(roomInfo?.room_number);
  const inGame = stage === 'PLAYING';

  // 标题动画入场
  useEffect(() => {
    const t = setTimeout(() => setTitleVisible(true), 300);
    return () => clearTimeout(t);
  }, []);

  // 登录/标题页面 BGM：页面加载时启动（可能被浏览器阻止，等待首次交互）
  useEffect(() => {
    if (appPhase === 'title' || appPhase === 'nameInput' || appPhase === 'roomSelect') {
      playBgm('lobby');
    }
  }, [appPhase]);

  // 全局首次点击解锁音频（BGM + TTS）
  useEffect(() => {
    const onFirstClick = () => {
      unlockAudio();
      if (appPhase === 'title' || appPhase === 'nameInput' || appPhase === 'roomSelect') {
        playBgm('lobby');
      }
    };
    document.addEventListener('click', onFirstClick, { once: true });
    return () => document.removeEventListener('click', onFirstClick);
  }, [appPhase]);

  // 全局点击恢复TTS（当浏览器阻止自动播放时）
  useEffect(() => {
    const handleClick = () => resumeTtsOnClick();
    document.addEventListener('click', handleClick);
    document.addEventListener('touchstart', handleClick);
    return () => {
      document.removeEventListener('click', handleClick);
      document.removeEventListener('touchstart', handleClick);
    };
  }, [resumeTtsOnClick]);

  // 自动滚动
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, privateMessages]);

  // waitingPhase 超时保护：如果超过 90 秒还没收到 stage_change，自动退出等待
  useEffect(() => {
    if (!waitingPhase) return;
    const timeoutId = setTimeout(() => {
      console.warn('⏰ waitingPhase 超时（90秒），自动退出等待');
      setWaitingPhase(false);
    }, 90000);
    return () => clearTimeout(timeoutId);
  }, [waitingPhase]);

  // 选项锁定超时保护：选选项后 30 秒没收到 DM 回复，自动解锁 UI
  useEffect(() => {
    if (optionTimeoutRef.current) {
      clearTimeout(optionTimeoutRef.current);
      optionTimeoutRef.current = null;
    }
    if (optionGenerating) {
      optionTimeoutRef.current = setTimeout(() => {
        console.warn('⏰ 选项锁定超时（30秒），自动解锁 UI');
        setOptionGenerating(false);
        setSelectedOptionIndex(null);
      }, 30000);
    }
    return () => {
      if (optionTimeoutRef.current) {
        clearTimeout(optionTimeoutRef.current);
        optionTimeoutRef.current = null;
      }
    };
  }, [optionGenerating]);

  // Socket 事件
  useEffect(() => {
    // 确保 socket 已连接
    if (!socket.connected) {
      socket.connect();
    }

    const onConnect = () => {
      setConnected(true);
      const savedName = localStorage.getItem('trpg_username');
      const savedRoom = localStorage.getItem('trpg_room');
      if (savedName && savedRoom) {
        setUserName(savedName);
        socket.emit('reconnect_room', {
          nickname: savedName,
          room_number: savedRoom,
        });
      }
    };

    // 如果已经连接，立即设置状态
    if (socket.connected) {
      setConnected(true);
    }

    socket.on('connect', onConnect);
    socket.on('disconnect', () => setConnected(false));

    socket.on('chat_message', (data) => {
      setMessages((prev) => [...prev, data]);
      // 新DM消息到达时重置选项选择状态
      if (data.user === 'DM' || data.user === 'DM-bot') {
        setSelectedOptionIndex(null);
        setOptionGenerating(false);
        // 每2条DM消息轮换背景图
        setDmMessageCount((prev) => {
          const next = prev + 1;
          if (next % 2 === 0) {
            setSceneBgIndex((idx) => (idx + 1) % SCENE_BACKGROUNDS.length);
          }
          return next;
        });
      }
    });

    socket.on('scene_update', (data) => {
      setScene(data);
      // 场景切换时自动切换背景音乐
      const bgmType = getSceneBgmType(data.name);
      playBgm(bgmType);
      setMessages((prev) => [
        ...prev,
        {
          user: '系统',
          content: `--- 场景切换：${data.name} ---`,
          time: new Date().toLocaleTimeString(),
        },
      ]);
    });

    socket.on('item_update', (data) => {
      setInventory((prev) => [...prev, data]);
      setMessages((prev) => [
        ...prev,
        {
          user: '系统',
          content: `获得线索：${data.name}`,
          time: new Date().toLocaleTimeString(),
        },
      ]);
    });

    socket.on('player_card', (data) => {
      setPlayerCard(data);
    });

    socket.on('private_message', (data) => {
      setPrivateMessages((prev) => [...prev, data]);
    });

    socket.on('dm_status', (data) => {
      setDmStatus(data.message || '');
    });

    socket.on('stage_change', (data) => {
      const newStage = data.to || 'IDLE';
      setStage(newStage);
      if (newStage === 'PLAYING') {
        setAppPhase('inGame');
        setWaitingPhase(false); // 游戏正式开始，结束等待
        setOptionGenerating(false);
        setSelectedOptionIndex(null);
        // 游戏开始，播放探索背景音
        playBgm('explore');
      } else if (newStage === 'LOBBY') {
        // 回到大厅
        playBgm('lobby');
      }
    });

    // 回合变更事件：切换BGM + 显示回合横幅动画
    const ROUND_BGM_CYCLE = ['explore', 'mystery', 'peaceful', 'tense', 'explore', 'combat', 'mystery'];
    socket.on('round_change', (data) => {
      const round = data.current_round || 0;
      const final = data.is_final_round || false;
      setCurrentRound(round);
      setIsFinalRound(final);
      // 显示回合切换横幅
      setShowRoundBanner(true);
      setTimeout(() => setShowRoundBanner(false), 2500);
      // 根据回合数从7种BGM中轮换
      const bgmIndex = (round - 1) % ROUND_BGM_CYCLE.length;
      const bgmType = ROUND_BGM_CYCLE[Math.max(0, bgmIndex)];
      playBgm(bgmType);
      // 系统消息
      setMessages((prev) => [
        ...prev,
        {
          user: '系统',
          content: final ? `--- 第 ${round} 回合（最终回合）---` : `--- 第 ${round} 回合 ---`,
          time: new Date().toLocaleTimeString(),
        },
      ]);
    });

    socket.on('game_generating', () => {
      setWaitingPhase(true);
    });

    socket.on('room_created', (data) => {
      setJoinError('');
      setCreatingRoom(false);
      setWaitingPhase(false);
      setRoomInfo(data);
      setRoomOwner(data.is_owner ? (nameInputValue.trim() || localStorage.getItem('trpg_username') || '') : '');
      setAppPhase('inGame');
      localStorage.setItem('trpg_room', data.room_number);
      // 进入房间后播放大厅背景音
      playBgm('lobby');
      // 使用当前最新的名字（从输入框或 localStorage）
      const savedName = nameInputValue.trim() || localStorage.getItem('trpg_username') || '';
      if (savedName) {
        localStorage.setItem('trpg_username', savedName);
        setUserName(savedName);
      }
    });

    socket.on('room_joined', (data) => {
      setJoinError('');
      setCreatingRoom(false);
      setWaitingPhase(false);
      setRoomInfo(data);
      // 加入房间后播放大厅背景音
      playBgm('lobby');
      setAppPhase('inGame');
      localStorage.setItem('trpg_room', data.room_number);
      const savedName = nameInputValue.trim() || localStorage.getItem('trpg_username') || '';
      if (savedName) {
        localStorage.setItem('trpg_username', savedName);
        setUserName(savedName);
      }
    });

    socket.on('join_error', (data) => {
      setCreatingRoom(false);
      setJoinError(data.message || '加入房间失败。');
      localStorage.removeItem('trpg_room');
    });

    socket.on('image_message', (data) => {
      if (data.url) {
        // 🔒 前端兜底：如果仍然是原始 HTTPS URL（说明后端转换失败），走代理 fetch 转 base64
        const rawUrl = data.url;
        if (rawUrl.startsWith('http://') || rawUrl.startsWith('https://')) {
          console.warn('⚠️ [前端拦截] 收到原始 URL，代理转 base64:', rawUrl.slice(0, 60));
          // 通过后端代理转换（避免 CORS 问题）
          fetch(`/api/proxy-image?url=${encodeURIComponent(rawUrl)}`)
            .then(r => r.text())
            .then(b64 => {
              if (b64.startsWith('data:')) {
                data.url = b64;
                applyImage(data);
              } else {
                console.warn('⚠️ 代理转换失败，丢弃');
              }
            })
            .catch(() => console.warn('⚠️ 代理 fetch 失败，丢弃原始 URL'));
          return;
        }
        applyImage(data);
      }
    });

    function applyImage(data) {
      const isAvatar = data.label && (data.label.includes('头像') || data.label.includes('角色'));
      if (isAvatar) {
        setPlayerAvatarUrl(data.url);
      } else {
        setBgTransitioning(false);
        setPrevBgImage('');
        setBackgroundImage(data.url);
      }
      setMessages((prev) => [
        ...prev,
        {
          user: '系统',
          content: data.label ? `📷 ${data.label}` : '📷 场景图片已更新',
          time: new Date().toLocaleTimeString(),
        },
      ]);
    }

    socket.on('room_state', (data) => {
      setRoomInfo({ room_number: data.room_number, room_name: data.room_name });
      setPlayers(data.players || []);
      setRoomOwner(data.owner_name || '');
      setStage(data.stage || 'IDLE');
      setScene(data.scene || scene);
      setSuggestions(data.suggestions || []);
      setRolePrefs(data.role_prefs || {});
      if (data.stage === 'PLAYING') setAppPhase('inGame');
    });

    socket.on('dice_event', (data) => {
      setDiceResult({
        result: data.result,
        success: data.success,
        reason: data.reason,
        show: true,
      });
      setTimeout(() => setDiceResult((prev) => (prev ? { ...prev, show: false } : null)), 4000);
    });

    socket.on('self_intro_start', (data) => {
      setSelfIntroActive(true);
      setSelfIntroDone(false);
    });

    socket.on('self_intro_complete', () => {
      setSelfIntroActive(false);
      setSelfIntroDone(false);
    });

    socket.on('tts_audio', (data) => {
      if (data.audio) {
        console.log('🎤 收到TTS语音, 队列长度:', audioQueueRef.current.length + 1);
        audioQueueRef.current.push(data);
        playNextAudio();
      }
    });

    socket.on('game_ending', (data) => {
      console.log('🃏 收到结局卡片数据:', data);
      // 🔒 前端兜底：如果 image_url 还是原始 HTTPS URL，代理转 base64
      if (data.image_url && (data.image_url.startsWith('http://') || data.image_url.startsWith('https://'))) {
        console.warn('⚠️ [前端拦截] 结局卡片含原始 URL，代理转 base64');
        fetch(`/api/proxy-image?url=${encodeURIComponent(data.image_url)}`)
          .then(r => r.text())
          .then(b64 => {
            if (b64.startsWith('data:')) {
              setGameEnding({ ...data, image_url: b64 });
            } else {
              setGameEnding({ ...data, image_url: null });
            }
            setShowEndingCard(true);
          })
          .catch(() => {
            setGameEnding({ ...data, image_url: null });
            setShowEndingCard(true);
          });
        return;
      }
      setGameEnding(data);
      setShowEndingCard(true);
    });

    return () => {
      socket.off('connect');
      socket.off('disconnect');
      socket.off('chat_message');
      socket.off('scene_update');
      socket.off('item_update');
      socket.off('player_card');
      socket.off('private_message');
      socket.off('dm_status');
      socket.off('stage_change');
      socket.off('room_created');
      socket.off('room_joined');
      socket.off('join_error');
      socket.off('image_message');
      socket.off('room_state');
      socket.off('dice_event');
      socket.off('game_generating');
      socket.off('self_intro_start');
      socket.off('self_intro_complete');
      socket.off('tts_audio');
      socket.off('game_ending');
    };
  }, [socket]);

  // 获取当前有效的玩家名（优先用最新输入）
  const currentName = nameInputValue.trim() || userName.trim();

  // 从开场页创建/加入房间
  const handleConfirmName = () => {
    const name = nameInputValue.trim();
    if (!name) {
      setJoinError('请输入你的玩家名。');
      return;
    }
    setUserName(name);
    localStorage.setItem('trpg_username', name);
    setJoinError('');
    setAppPhase('roomSelect');
  };

  const createRoom = useCallback(() => {
    const name = nameInputValue.trim() || userName.trim();
    if (!name || creatingRoom) return;
    // 确保 socket 已连接，否则先连接
    if (!socket.connected) {
      socket.connect();
      setTimeout(() => {
        if (!socket.connected) {
          setCreatingRoom(false);
          setJoinError('无法连接服务器，请刷新页面后重试。');
          return;
        }
        doCreateRoom(name);
      }, 2000);
      return;
    }
    doCreateRoom(name);
  }, [nameInputValue, userName, socket, creatingRoom]);

  const doCreateRoom = (name) => {
    setCreatingRoom(true);
    setMessages([]);
    setPrivateMessages([]);
    setPlayerCard(null);
    setBackgroundImage('/灵感收集大厅.png');
    setDmMessageCount(0);
    setSceneBgIndex(0);
    socket.emit('create_room', { nickname: name });

    const timeoutId = setTimeout(() => {
      setCreatingRoom(false);
      setJoinError('创建房间超时，请检查服务器连接后重试。');
    }, 10000);

    const onRoomCreated = () => {
      clearTimeout(timeoutId);
      setCreatingRoom(false);
    };
    const onJoinError = () => {
      clearTimeout(timeoutId);
      setCreatingRoom(false);
    };
    socket.once('room_created', onRoomCreated);
    socket.once('join_error', onJoinError);
  };

  const createFestivalRoom = useCallback(() => {
    const name = nameInputValue.trim() || userName.trim();
    if (!name || creatingRoom) return;
    if (!socket.connected) {
      socket.connect();
      setTimeout(() => {
        if (!socket.connected) {
          setCreatingRoom(false);
          setJoinError('无法连接服务器，请刷新页面后重试。');
          return;
        }
        doCreateFestival(name);
      }, 2000);
      return;
    }
    doCreateFestival(name);
  }, [nameInputValue, userName, socket, creatingRoom]);

  const doCreateFestival = (name) => {
    setCreatingRoom(true);
    setMessages([]);
    setPrivateMessages([]);
    setPlayerCard(null);
    setBackgroundImage('/灵感收集大厅.png');
    setDmMessageCount(0);
    setSceneBgIndex(0);
    socket.emit('create_festival_room', { nickname: name });

    const timeoutId = setTimeout(() => {
      setCreatingRoom(false);
      setJoinError('端午特辑启动超时，请检查服务器连接后重试。');
    }, 15000);

    const onRoomCreated = () => {
      clearTimeout(timeoutId);
      setCreatingRoom(false);
    };
    const onJoinError = () => {
      clearTimeout(timeoutId);
      setCreatingRoom(false);
    };
    socket.once('room_created', onRoomCreated);
    socket.once('join_error', onJoinError);
  };

  const joinRoom = useCallback(() => {
    const name = nameInputValue.trim() || userName.trim();
    if (!name || creatingRoom) return;
    const roomNum = joinRoomInput.trim() || roomNumberInput.trim();
    if (!roomNum) {
      setJoinError('请输入房间号。');
      return;
    }
    if (!socket.connected) {
      socket.connect();
      setTimeout(() => {
        if (!socket.connected) {
          setCreatingRoom(false);
          setJoinError('无法连接服务器，请刷新页面后重试。');
          return;
        }
        doJoinRoom(name, roomNum);
      }, 2000);
      return;
    }
    doJoinRoom(name, roomNum);
  }, [nameInputValue, userName, joinRoomInput, roomNumberInput, socket, creatingRoom]);

  const doJoinRoom = (name, roomNum) => {
    setCreatingRoom(true);
    setMessages([]);
    setPrivateMessages([]);
    setPlayerCard(null);
    setBackgroundImage('/灵感收集大厅.png');
    setDmMessageCount(0);
    setSceneBgIndex(0);
    socket.emit('join_room', { nickname: name, room_number: roomNum });

    const timeoutId = setTimeout(() => {
      setCreatingRoom(false);
      setJoinError('加入房间超时，请检查房间号或服务器连接后重试。');
    }, 10000);

    const onRoomJoined = () => {
      clearTimeout(timeoutId);
      setCreatingRoom(false);
    };
    const onJoinError = () => {
      clearTimeout(timeoutId);
      setCreatingRoom(false);
    };
    socket.once('room_joined', onRoomJoined);
    socket.once('join_error', onJoinError);
  };

  const handleSend = useCallback(
    (text) => {
      const msg = typeof text === 'string' ? text : inputText;
      if (!msg.trim()) return;
      clearTtsQueue(); // 清空旧TTS队列，让新内容朗读与画面同步
      socket.emit('send_message', { content: msg });
      setInputText('');
    },
    [inputText, socket, clearTtsQueue],
  );

  const submitPreference = useCallback(() => {
    if (!worldviewPref.trim() && !rolePref.trim()) {
      setJoinError('请至少填写世界观建议或角色偏好。');
      return;
    }
    playButtonSound('success');
    socket.emit('submit_preference', {
      worldview: worldviewPref,
      role: rolePref,
    });
    setWorldviewPref('');
    setRolePref('');
    // 明确提示：提交意向即报名成功
    setJoinError('✅ 你的意向已提交，报名成功！等待所有玩家提交后即可开始游戏。');
    setTimeout(() => setJoinError(''), 5000);
  }, [worldviewPref, rolePref, socket]);

  const startGame = useCallback(() => {
    // 解锁浏览器音频自动播放（需要用户手势上下文）
    unlockAudio();
    playButtonSound('confirm');
    setWaitingPhase(true);
    socket.emit('start_game', { total_rounds: totalRounds });
  }, [socket, totalRounds]);

  const leaveRoom = useCallback(() => {
    stopBgm(); // 离开房间时停止背景音乐
    localStorage.removeItem('trpg_room');
    setRoomInfo(null);
    setRoomOwner('');
    setMessages([]);
    setPrivateMessages([]);
    setPlayerCard(null);
    setInventory([]);
    setBackgroundImage('/灵感收集大厅.png');
    setScene({ name: '等待开场', description: '请创建或加入一个网页房间。' });
    setStage('IDLE');
    setPlayers([]);
    setSuggestions([]);
    setRolePrefs({});
    setAppPhase('title');
    setJoinRoomInput('');
    setRoomNumberInput('');
    setNameInputValue('');
    setRoomMode(null);
    setCreatingRoom(false);
    setWaitingPhase(false);
    setSelectedOptionIndex(null);
    setOptionGenerating(false);
    setPlayerAvatarUrl('');
    setWaitingPhase(false);
    setDmMessageCount(0);
    setSceneBgIndex(0);
    setShowAvatarModal(false);
    setSelfIntroActive(false);
    setSelfIntroDone(false);
  }, []);

  // 从结局卡片返回大厅（房间选择界面）
  const returnToLobby = useCallback(() => {
    stopBgm();
    // 广播离开房间
    socket.emit('leave_room', { nickname: userName, room_number: roomInfo?.room_number });
    localStorage.removeItem('trpg_room');
    setRoomInfo(null);
    setRoomOwner('');
    setMessages([]);
    setPrivateMessages([]);
    setPlayerCard(null);
    setInventory([]);
    setBackgroundImage('/灵感收集大厅.png');
    setScene({ name: '等待开场', description: '请创建或加入一个网页房间。' });
    setStage('IDLE');
    setPlayers([]);
    setSuggestions([]);
    setRolePrefs({});
    setShowEndingCard(false);
    setGameEnding(null);
    setDmMessageCount(0);
    setSceneBgIndex(0);
    clearTtsQueue();
    // 回到房间选择界面，保留玩家名
    setAppPhase('roomSelect');
    setJoinRoomInput('');
    setRoomNumberInput('');
    setRoomMode(null);
    setCreatingRoom(false);
    setWaitingPhase(false);
    setSelectedOptionIndex(null);
    setOptionGenerating(false);
    setPlayerAvatarUrl('');
    setShowAvatarModal(false);
    setSelfIntroActive(false);
    setSelfIntroDone(false);
  }, [socket, userName, roomInfo, stopBgm, clearTtsQueue]);

  // ========== 最新DM消息（用于中间剧情区显示） ==========
  const latestDmMessage = useMemo(() => {
    const dmMsgs = messages.filter((m) => m.user === 'DM' || m.user === 'DM-bot');
    return dmMsgs.length > 0 ? dmMsgs[dmMsgs.length - 1] : null;
  }, [messages]);

  const latestDmOptions = useMemo(() => {
    if (!latestDmMessage) return [];
    return parseOptions(latestDmMessage.content);
  }, [latestDmMessage]);

  const latestDmBody = useMemo(() => {
    if (!latestDmMessage) return '';
    return stripOptions(latestDmMessage.content);
  }, [latestDmMessage]);

  // ========== 渲染：标题画面 ==========
  if (appPhase === 'title') {
    return (
      <div className="flex h-screen bg-[#0a0a1a] text-white overflow-hidden relative select-none">
        <ParticleBackground />

        {/* 中央标题区域 */}
        <div className="relative z-10 flex flex-col items-center justify-center w-full">
          {/* 装饰光环 */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full bg-gradient-radial from-blue-500/5 via-transparent to-transparent animate-pulse pointer-events-none" />

          {/* 副标题 */}
          <div
            className={`text-sm tracking-[0.6em] text-blue-300/50 mb-6 uppercase transition-all duration-1000 ${
              titleVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
            }`}
          >
            沉浸式 AI 跑团体验
          </div>

          {/* 主标题《捕梦》 */}
          <h1
            className={`text-[7rem] font-serif font-bold tracking-wider mb-8 transition-all duration-1000 delay-200 ${
              titleVisible ? 'opacity-100 scale-100' : 'opacity-0 scale-90'
            }`}
            style={{
              background: 'linear-gradient(135deg, #93c5fd 0%, #a78bfa 30%, #f9a8d4 60%, #93c5fd 100%)',
              backgroundSize: '200% 200%',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              animation: 'gradientShift 4s ease-in-out infinite',
              filter: 'drop-shadow(0 0 40px rgba(147, 197, 253, 0.3))',
            }}
          >
            捕 梦
          </h1>

          {/* 描述文字 */}
          <p
            className={`text-slate-400 text-sm text-center max-w-md leading-relaxed mb-12 transition-all duration-1000 delay-500 ${
              titleVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
            }`}
          >
            每一个梦境都是一段未被讲述的故事
            <br />
            你准备好了吗？
          </p>

          {/* 开始游戏按钮 */}
          <button
            onClick={() => { playButtonSound('confirm'); setAppPhase('nameInput'); }}
            className={`group relative px-12 py-4 rounded-full text-lg font-bold tracking-wider
              bg-gradient-to-r from-blue-600/80 via-purple-600/80 to-pink-600/80
              hover:from-blue-500 hover:via-purple-500 hover:to-pink-500
              shadow-lg shadow-blue-500/20 hover:shadow-blue-500/40
              transition-all duration-1000 delay-700
              ${titleVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}
          >
            <span className="relative z-10">开 始 游 戏</span>
            <div className="absolute inset-0 rounded-full bg-gradient-to-r from-blue-400 via-purple-400 to-pink-400 opacity-0 group-hover:opacity-20 blur-xl transition-opacity" />
          </button>

          {/* 底部连接状态 */}
          <div
            className={`absolute bottom-8 text-xs transition-all duration-1000 delay-1000 ${
              titleVisible ? 'opacity-100' : 'opacity-0'
            }`}
          >
            <span className={connected ? 'text-green-400/60' : 'text-red-400/60'}>
              {connected ? '● 服务器已连接' : '○ 正在连接服务器...'}
            </span>
          </div>
        </div>
      </div>
    );
  }

  // ========== 渲染：输入玩家名 ==========
  if (appPhase === 'nameInput') {
    return (
      <div className="flex h-screen bg-[#0a0a1a] text-white overflow-hidden relative select-none">
        <ParticleBackground />
        <div className="relative z-10 flex flex-col items-center justify-center w-full">
          {/* 顶部标题 */}
          <div
            className="absolute top-10 left-1/2 -translate-x-1/2 cursor-pointer group"
            onClick={() => { playButtonSound('cancel'); setAppPhase('title'); }}
          >
            <h2
              className="text-3xl font-serif font-bold tracking-widest opacity-40 group-hover:opacity-60 transition-opacity"
              style={{
                background: 'linear-gradient(135deg, #93c5fd, #a78bfa)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}
            >
              捕 梦
            </h2>
          </div>

          <div className="w-[400px] bg-slate-900/60 backdrop-blur-xl border border-slate-700/40 rounded-2xl p-8 shadow-2xl animate-[fadeSlideUp_0.6s_ease-out]">
            <h3 className="text-xl font-bold text-center mb-2 text-slate-200">你是谁？</h3>
            <p className="text-xs text-slate-500 text-center mb-6">输入你的名字，开始冒险</p>

            <input
              type="text"
              className="w-full bg-slate-800/80 border border-slate-600/50 rounded-xl px-5 py-3.5 text-white text-center text-lg
                focus:outline-none focus:border-blue-400/60 focus:ring-2 focus:ring-blue-500/20
                placeholder:text-slate-600 transition-all"
              placeholder="输入你的玩家名..."
              value={nameInputValue}
              onChange={(e) => { playTypingSound(); setNameInputValue(e.target.value); }}
              onKeyDown={(e) => { if (e.key === 'Enter') { playButtonSound('confirm'); handleConfirmName(); } }}
              autoFocus
            />

            {joinError && <p className="text-red-400 text-xs mt-3 text-center">{joinError}</p>}

            <button
              onClick={() => { playButtonSound('confirm'); handleConfirmName(); }}
              className="w-full mt-5 py-3 rounded-xl bg-gradient-to-r from-blue-600 to-purple-600
                hover:from-blue-500 hover:to-purple-500 font-bold text-sm tracking-wider
                shadow-lg shadow-blue-500/20 transition-all active:scale-[0.98]"
            >
              确 认
            </button>

            <button
              onClick={() => { playButtonSound('cancel'); setAppPhase('title'); }}
              className="w-full mt-3 py-2 text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              返回
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ========== 渲染：选择创建/加入房间 ==========
  if (appPhase === 'roomSelect') {
    return (
      <div className="flex h-screen bg-[#0a0a1a] text-white overflow-hidden relative select-none">
        <ParticleBackground />
        <div className="relative z-10 flex flex-col items-center justify-center w-full">
          {/* 顶部标题 */}
          <div
            className="absolute top-10 left-1/2 -translate-x-1/2 cursor-pointer group"
            onClick={() => { playButtonSound('cancel'); setAppPhase('title'); }}
          >
            <h2
              className="text-3xl font-serif font-bold tracking-widest opacity-40 group-hover:opacity-60 transition-opacity"
              style={{
                background: 'linear-gradient(135deg, #93c5fd, #a78bfa)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}
            >
              捕 梦
            </h2>
          </div>

          <div className="w-[420px] bg-slate-900/60 backdrop-blur-xl border border-slate-700/40 rounded-2xl p-8 shadow-2xl animate-[fadeSlideUp_0.6s_ease-out]">
            <div className="text-center mb-6">
              <div className="text-xs text-blue-300/60 mb-1">玩家</div>
              <div className="text-lg font-bold text-slate-200">{nameInputValue}</div>
            </div>

            <div className="grid grid-cols-2 gap-4 mb-6">
              <button
                onClick={() => {
                  playButtonSound('confirm');
                  setRoomMode('create');
                  createRoom();
                }}
                disabled={creatingRoom}
                className={`relative group py-6 rounded-xl bg-gradient-to-br from-blue-900/40 to-blue-800/20
                  border border-blue-500/20 hover:border-blue-400/40
                  transition-all hover:scale-[1.02] active:scale-[0.98]
                  ${creatingRoom ? 'opacity-60 cursor-wait' : ''}`}
              >
                <div className="text-3xl mb-2">{creatingRoom && roomMode === 'create' ? '⏳' : '🏰'}</div>
                <div className="text-sm font-bold text-blue-300">
                  {creatingRoom && roomMode === 'create' ? '创建中...' : '创建房间'}
                </div>
                <div className="text-[10px] text-blue-400/40 mt-1">开启新的冒险</div>
              </button>

              <button
                onClick={() => { playButtonSound('click'); setRoomMode('join'); }}
                disabled={creatingRoom}
                className={`relative group py-6 rounded-xl bg-gradient-to-br from-purple-900/40 to-purple-800/20
                  border border-purple-500/20 hover:border-purple-400/40
                  transition-all hover:scale-[1.02] active:scale-[0.98]
                  ${creatingRoom ? 'opacity-60 cursor-wait' : ''}`}
              >
                <div className="text-3xl mb-2">🚪</div>
                <div className="text-sm font-bold text-purple-300">加入房间</div>
                <div className="text-[10px] text-purple-400/40 mt-1">加入朋友的冒险</div>
              </button>
            </div>

            {/* 端午特辑快速游戏 */}
            <button
              onClick={() => {
                playButtonSound('confirm');
                unlockAudio();
                setRoomMode('festival');
                createFestivalRoom();
              }}
              disabled={creatingRoom}
              className={`w-full relative group py-4 mb-6 rounded-xl overflow-hidden
                bg-gradient-to-r from-emerald-900/60 via-teal-800/40 to-emerald-900/60
                hover:from-emerald-800/60 hover:via-teal-700/50 hover:to-emerald-800/60
                border border-emerald-400/30 hover:border-emerald-300/50
                transition-all hover:scale-[1.01] active:scale-[0.98]
                ${creatingRoom ? 'opacity-60 cursor-wait' : ''}`}
            >
              {/* 装饰底纹 */}
              <div className="absolute inset-0 opacity-20"
                style={{
                  backgroundImage: 'repeating-linear-gradient(45deg, transparent, transparent 10px, rgba(52,211,153,0.1) 10px, rgba(52,211,153,0.1) 11px)',
                }} />
              <div className="relative z-10 flex items-center justify-center gap-3">
                <span className="text-2xl">🐉</span>
                <div className="text-left">
                  <div className="text-base font-bold text-emerald-200 tracking-wide">
                    {creatingRoom && roomMode === 'festival' ? '🐲 正在加载龙舟...' : '端午特辑'}
                  </div>
                  <div className="text-[10px] text-emerald-400/50 mt-0.5">点击快速游戏 · 「端午到，龙舟跑」</div>
                </div>
                <span className="text-emerald-400/40 text-lg">{creatingRoom && roomMode === 'festival' ? '⏳' : '⚡'}</span>
              </div>
            </button>

            {roomMode === 'join' && (
              <div className="animate-[fadeSlideUp_0.3s_ease-out] space-y-3">
                <input
                  type="text"
                  className="w-full bg-slate-800/80 border border-slate-600/50 rounded-xl px-5 py-3 text-white text-center
                    focus:outline-none focus:border-purple-400/60 focus:ring-2 focus:ring-purple-500/20
                    placeholder:text-slate-600 transition-all"
                  placeholder="输入房间号..."
                  value={joinRoomInput}
                  onChange={(e) => { playTypingSound(); setJoinRoomInput(e.target.value); }}
                  onKeyDown={(e) => { if (e.key === 'Enter') { playButtonSound('confirm'); joinRoom(); } }}
                  autoFocus
                  disabled={creatingRoom}
                />
                <button
                  onClick={() => { playButtonSound('confirm'); joinRoom(); }}
                  disabled={creatingRoom}
                  className={`w-full py-3 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600
                    hover:from-purple-500 hover:to-pink-500 font-bold text-sm tracking-wider
                    shadow-lg shadow-purple-500/20 transition-all active:scale-[0.98]
                    ${creatingRoom ? 'opacity-60 cursor-wait' : ''}`}
                >
                  {creatingRoom ? '加入中...' : '加入房间'}
                </button>
              </div>
            )}

            {joinError && <p className="text-red-400 text-xs mt-4 text-center">{joinError}</p>}

            <button
              onClick={() => {
                playButtonSound('cancel');
                setAppPhase('nameInput');
                setRoomMode(null);
                setJoinError('');
              }}
              className="w-full mt-4 py-2 text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              返回修改玩家名
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ========== 等待页面：全屏独立显示，不显示任何边栏 ==========
  if (waitingPhase) {
    return (
      <div className="fixed inset-0 z-[999] bg-[#0a0a1a] flex items-center justify-center overflow-hidden">
        <ParticleBackground />
        
        {/* 深色氛围渐变 */}
        <div className="absolute inset-0 bg-gradient-to-b from-[#0a0a1a]/60 via-transparent to-[#0a0a1a]/85 pointer-events-none" />

        {/* ===== 外层大旋转光环 ===== */}
        <div className="absolute w-[500px] h-[500px] rounded-full border border-blue-500/10 animate-[waitingSpin_12s_linear_infinite]"
          style={{ boxShadow: '0 0 80px rgba(59, 130, 246, 0.08), inset 0 0 80px rgba(59, 130, 246, 0.05)' }} />
        <div className="absolute w-[420px] h-[420px] rounded-full border border-purple-500/8 animate-[waitingSpinReverse_10s_linear_infinite]" />

        {/* ===== 中层旋转光弧（分段） ===== */}
        <div className="absolute w-[340px] h-[340px] rounded-full border-2 border-transparent border-t-blue-400/20 border-r-transparent border-b-purple-400/20 border-l-transparent animate-[waitingSpin_5s_linear_infinite]" />
        <div className="absolute w-[280px] h-[280px] rounded-full border-2 border-transparent border-t-purple-400/15 border-r-blue-400/15 border-b-transparent border-l-transparent animate-[waitingSpinReverse_4s_linear_infinite]" />

        {/* ===== 构建进度环（从左到右逐段亮起） ===== */}
        <svg className="absolute w-[220px] h-[220px] -rotate-90" viewBox="0 0 220 220">
          {/* 背景轨道 */}
          <circle cx="110" cy="110" r="105" fill="none" stroke="rgba(148, 163, 184, 0.08)" strokeWidth="2" />
          {/* 5段弧形，从左到右依次闪烁 */}
          {[0, 1, 2, 3, 4].map((i) => {
            const startAngle = i * 72 - 90;
            const endAngle = startAngle + 60;
            const startRad = (startAngle * Math.PI) / 180;
            const endRad = (endAngle * Math.PI) / 180;
            const r = 105;
            const x1 = 110 + r * Math.cos(startRad);
            const y1 = 110 + r * Math.sin(startRad);
            const x2 = 110 + r * Math.cos(endRad);
            const y2 = 110 + r * Math.sin(endRad);
            const largeArc = endAngle - startAngle > 180 ? 1 : 0;
            return (
              <path
                key={i}
                d={`M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`}
                fill="none"
                stroke="url(#gradArc)"
                strokeWidth="2.5"
                strokeLinecap="round"
                style={{
                  animation: `arcLight 2s ease-in-out ${i * 0.4}s infinite`,
                  opacity: 0,
                }}
              />
            );
          })}
          <defs>
            <linearGradient id="gradArc" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#60a5fa" />
              <stop offset="100%" stopColor="#a78bfa" />
            </linearGradient>
          </defs>
        </svg>

        {/* ===== 中心内容 ===== */}
        <div className="relative z-10 flex flex-col items-center">
          {/* Logo - 带光环 */}
          <div className="mb-8 relative">
            <div className="absolute inset-0 rounded-full border border-blue-400/20 animate-[waitingSpin_4s_linear_infinite]"
              style={{ transform: 'scale(1.5)' }} />
            <div className="absolute inset-0 rounded-full border border-purple-400/10 animate-[waitingSpinReverse_3s_linear_infinite]"
              style={{ transform: 'scale(1.8)' }} />
            <div className="w-24 h-24 animate-[logoFloat_3s_ease-in-out_infinite,logoGlow_2s_ease-in-out_infinite] relative">
              <img
                src="/logo.png"
                alt="捕梦"
                className="w-full h-full object-contain drop-shadow-[0_0_25px_rgba(147,197,253,0.5)]"
                onError={(e) => {
                  e.target.style.display = 'none';
                  // fallback: 显示文字logo
                  const parent = e.target.parentElement;
                  if (parent && !parent.querySelector('.logo-fallback')) {
                    const fallback = document.createElement('div');
                    fallback.className = 'logo-fallback w-full h-full rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-3xl font-bold shadow-lg shadow-blue-500/20';
                    fallback.textContent = '捕';
                    parent.appendChild(fallback);
                  }
                }}
              />
            </div>
          </div>

          {/* 状态文字 */}
          <div className="text-center space-y-4">
            <h2 className="text-2xl font-serif font-bold tracking-wider animate-[waitingTextBreathe_2s_ease-in-out_infinite]"
              style={{
                background: 'linear-gradient(135deg, #93c5fd 0%, #a78bfa 50%, #93c5fd 100%)',
                backgroundSize: '200% 100%',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                animation: 'waitingTextBreathe 2s ease-in-out infinite, gradientShift 3s linear infinite',
              }}>
              DM 正在构筑梦境...
            </h2>
            <p className="text-sm text-slate-500 animate-[waitingTextBreathe_3s_ease-in-out_infinite]" style={{ animationDelay: '0.5s' }}>
              正在编织命运之线...
            </p>
          </div>

          {/* 构建步骤指示器（5段，从左到右依次亮起） */}
          <div className="flex items-center gap-2 mt-10">
            {['生成剧本', '分配身份', '构筑场景', '编排事件', '准备就绪'].map((label, i) => (
              <div key={i} className="flex items-center gap-2">
                <div className="flex flex-col items-center gap-1.5">
                  <div
                    className="w-2.5 h-2.5 rounded-full"
                    style={{
                      background: 'linear-gradient(135deg, #60a5fa, #a78bfa)',
                      boxShadow: '0 0 12px rgba(96, 165, 250, 0.6)',
                      animation: `buildStep 2.5s ease-in-out ${i * 0.5}s infinite`,
                      opacity: 0,
                    }}
                  />
                  <span className="text-[9px] text-slate-500 whitespace-nowrap"
                    style={{ animation: `waitingTextBreathe 2.5s ease-in-out ${i * 0.5}s infinite` }}>
                    {label}
                  </span>
                </div>
                {i < 4 && (
                  <div className="w-6 h-px bg-slate-700/50 mb-4"
                    style={{ animation: `lineGlow 2.5s ease-in-out ${i * 0.5}s infinite` }} />
                )}
              </div>
            ))}
          </div>

          {/* 底部闪烁光条 */}
          <div className="w-64 h-0.5 bg-slate-800/50 rounded-full mt-12 overflow-hidden">
            <div className="h-full bg-gradient-to-r from-blue-500/0 via-blue-400/60 to-blue-500/0 rounded-full animate-[progressShine_2s_ease-in-out_infinite]" />
          </div>

          {/* 提示文字 */}
          <p className="text-[10px] text-slate-600 mt-6 animate-[waitingTextBreathe_4s_ease-in-out_infinite]">
            身份牌分配中，请耐心等待...
          </p>
        </div>

        {/* 装饰性角落光效 */}
        <div className="absolute top-0 left-1/4 w-px h-32 bg-gradient-to-b from-blue-400/20 to-transparent animate-pulse" />
        <div className="absolute top-0 right-1/4 w-px h-24 bg-gradient-to-b from-purple-400/15 to-transparent animate-pulse" style={{ animationDelay: '0.5s' }} />
      </div>
    );
  }

  // ========== 自我介绍页面：全屏显示 ==========
  if (selfIntroActive && !selfIntroDone) {
    return (
      <div className="fixed inset-0 z-[999] bg-[#0a0a1a] flex items-center justify-center overflow-hidden">
        <ParticleBackground />
        <div className="absolute inset-0 bg-gradient-to-b from-[#0a0a1a]/40 via-transparent to-[#0a0a1a]/80 pointer-events-none" />

        {/* 装饰旋转光环 */}
        <div className="absolute w-[400px] h-[400px] rounded-full border border-purple-500/10 animate-[waitingSpin_10s_linear_infinite]"
          style={{ boxShadow: '0 0 60px rgba(139, 92, 246, 0.06)' }} />
        <div className="absolute w-[320px] h-[320px] rounded-full border border-blue-500/8 animate-[waitingSpinReverse_8s_linear_infinite]" />

        <div className="relative z-10 flex flex-col items-center max-w-lg w-full px-8">
          {/* 角色卡展示 */}
          <div className="w-full bg-slate-900/60 backdrop-blur-xl border border-purple-500/20 rounded-2xl p-8 shadow-2xl animate-[fadeSlideUp_0.5s_ease-out]">
            {/* 头像区 */}
            <div className="flex justify-center mb-6">
              {playerAvatarUrl ? (
                <div className="w-24 h-24 rounded-full overflow-hidden ring-2 ring-purple-400/30 shadow-lg shadow-purple-500/20">
                  <img src={playerAvatarUrl} alt="角色头像" className="w-full h-full object-cover" />
                </div>
              ) : (
                <div className="w-24 h-24 rounded-full bg-gradient-to-br from-purple-500 to-blue-600 flex items-center justify-center text-3xl font-bold shadow-lg shadow-purple-500/20">
                  {playerCard?.role_name?.[0] || '?'}
                </div>
              )}
            </div>

            {/* 角色信息 */}
            <div className="text-center space-y-3 mb-8">
              <h2 className="text-2xl font-serif font-bold"
                style={{
                  background: 'linear-gradient(135deg, #a78bfa, #93c5fd)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                }}>
                {playerCard?.role_name || '未知角色'}
              </h2>
              <p className="text-sm text-slate-400">{playerCard?.identity || ''}</p>
              {playerCard?.public_bio && (
                <p className="text-xs text-slate-500 italic leading-relaxed mt-2 px-4 py-3 bg-slate-800/50 rounded-xl border border-slate-700/30">
                  "{playerCard.public_bio}"
                </p>
              )}
            </div>

            {/* 引导语 */}
            <div className="text-center mb-6">
              <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-purple-900/30 border border-purple-500/20 text-purple-300/80 text-xs">
                <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
                自我介绍环节
              </div>
              <p className="text-xs text-slate-500 mt-3">
                请向其他玩家介绍你的角色身份与背景故事
              </p>
            </div>

            {/* 完成按钮 */}
            <button
              onClick={() => {
                playButtonSound('confirm');
                setSelfIntroDone(true);
                socket.emit('self_intro_done', {});
              }}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-purple-600/80 to-blue-600/80
                hover:from-purple-500 hover:to-blue-500 font-bold text-sm tracking-wider
                shadow-lg shadow-purple-500/20 transition-all active:scale-[0.98]
                border border-purple-400/20"
            >
              完成自我介绍
            </button>
          </div>
        </div>

        {/* 底部提示 */}
        <div className="absolute bottom-10 text-[10px] text-slate-600">
          等待所有玩家完成自我介绍...
        </div>
      </div>
    );
  }

  // ========== 主游戏界面 ==========
  return (
    <div className="flex h-screen bg-[#0a0a1a] text-white overflow-hidden relative">
      <ParticleBackground />

      {/* ===== 场景背景层（全屏） ===== */}
      {/* CSS渐变底层（始终显示，每2轮DM消息切换） */}
      <div
        className="absolute inset-0 z-0 transition-all duration-1500"
        style={{
          background: SCENE_BACKGROUNDS[sceneBgIndex],
          opacity: 0.5,
        }}
      />
      {/* 图片叠加层（有图片URL时显示） */}
      {/* 旧图淡出层 */}
      {bgTransitioning && prevBgImage && (
        <div
          className="absolute inset-0 z-0 transition-opacity duration-1500"
          style={{
            backgroundImage: `url(${prevBgImage})`,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
            backgroundRepeat: 'no-repeat',
            opacity: 0,
          }}
        />
      )}
      {/* 新图淡入层 */}
      {backgroundImage && (
        <div
          className="absolute inset-0 z-0 transition-opacity duration-1500"
          style={{
            backgroundImage: `url(${backgroundImage})`,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
            backgroundRepeat: 'no-repeat',
            opacity: bgTransitioning ? 0.45 : 0.45,
          }}
        />
      )}
      {/* 深色遮罩 */}
      <div className="absolute inset-0 z-[1] bg-gradient-to-b from-[#0a0a1a]/60 via-transparent to-[#0a0a1a]/85 pointer-events-none" />

      {/* ===== 骰子结果动画 ===== */}
      {diceResult?.show && (
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 animate-[diceRoll_0.5s_ease-out] pointer-events-none">
          <div
            className={`p-6 rounded-2xl backdrop-blur-xl border-2 ${
              diceResult.success
                ? 'bg-emerald-900/60 border-emerald-500/50'
                : 'bg-red-900/60 border-red-500/50'
            }`}
          >
            <div className="text-center">
              <div className={`text-5xl font-bold mb-2 ${diceResult.success ? 'text-emerald-300' : 'text-red-300'}`}>
                🎲 {diceResult.result}
              </div>
              <div className={`text-lg font-bold mb-1 ${diceResult.success ? 'text-emerald-400' : 'text-red-400'}`}>
                {diceResult.success ? '✅ 成功' : '❌ 失败'}
              </div>
              <div className="text-xs text-slate-300 max-w-48">{diceResult.reason}</div>
            </div>
          </div>
        </div>
      )}

      {/* ===== 左侧面板切换按钮 ===== */}
      <button
        onClick={() => { playButtonSound('click'); setShowLeftPanel(!showLeftPanel); }}
        className="absolute top-1/2 -translate-y-1/2 left-0 z-40 bg-slate-900/50 hover:bg-slate-800/70
          border border-slate-600/20 rounded-r-lg px-1.5 py-5 text-slate-400 hover:text-slate-200
          transition-all backdrop-blur-sm"
        title={showLeftPanel ? '收起角色面板' : '展开角色面板'}
      >
        {showLeftPanel ? '◀' : '▶'}
      </button>

      {/* ===== 左侧面板：角色卡 + 私密情报 ===== */}
      <div
        className={`h-full flex flex-col shrink-0 transition-all duration-300 ease-in-out overflow-hidden
          bg-slate-900/80 backdrop-blur-xl border-r border-slate-700/20 z-10
          ${showLeftPanel ? (isMobile ? 'w-[85vw]' : 'w-72') : 'w-0 border-r-0'}`}
      >
        {/* 角色卡区域 */}
        <div className="p-4 border-b border-slate-700/20 shrink-0">
          {playerCard ? (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                {playerAvatarUrl ? (
                  <div
                    className="w-11 h-11 rounded-full overflow-hidden shrink-0 shadow-lg shadow-blue-500/30 ring-2 ring-blue-400/30 cursor-pointer hover:ring-blue-300/60 hover:shadow-blue-500/50 transition-all active:scale-95"
                    onClick={() => { playButtonSound('click'); setShowAvatarModal(true); }}
                    title="点击查看大图"
                  >
                    <img src={playerAvatarUrl} alt={playerCard.role_name} className="w-full h-full object-cover" />
                  </div>
                ) : (
                  <div className="w-11 h-11 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-xl font-bold shrink-0 shadow-lg shadow-blue-500/20">
                    {playerCard.role_name?.[0] || '?'}
                  </div>
                )}
                <div className="min-w-0">
                  <div className="text-sm font-bold text-blue-300 truncate">{playerCard.role_name}</div>
                  <div className="text-[10px] text-slate-500">@{userName}</div>
                </div>
              </div>

              {playerCard.secret && (
                <div className="bg-red-950/30 border border-red-800/30 rounded-lg p-3">
                  <div className="text-[10px] font-bold text-red-400 mb-1">核心秘密</div>
                  <p className="text-[11px] text-red-200/70 leading-relaxed line-clamp-3">
                    {cleanMarkdown(playerCard.secret)}
                  </p>
                </div>
              )}

              {playerCard.background && (
                <details className="text-[11px]">
                  <summary className="text-slate-400 cursor-pointer hover:text-slate-300">角色背景</summary>
                  <p className="text-slate-300 mt-1 leading-relaxed">{cleanMarkdown(playerCard.background)}</p>
                </details>
              )}
            </div>
          ) : (
            <p className="text-slate-500 text-xs text-center py-4">等待分配角色...</p>
          )}
        </div>

        {/* 私密情报 */}
        <div className="flex-1 flex flex-col min-h-0">
          <div className="px-4 py-2 border-b border-slate-700/20 bg-slate-800/20 flex items-center justify-between shrink-0">
            <span className="text-[11px] font-bold text-slate-300">私密情报</span>
            <span className="text-[10px] text-slate-500">{privateMessages.length}条</span>
          </div>
          <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
            {privateMessages.length === 0 ? (
              <p className="text-slate-500 text-xs text-center py-6">暂无</p>
            ) : (
              privateMessages.map((msg, i) => {
                const parsed = parsePrivateMessage(msg.content);
                return (
                  <div key={i} className="bg-amber-950/20 border border-amber-800/20 rounded-lg p-2.5">
                    <div className="flex items-center gap-1.5 mb-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-500/40" />
                      <span className="text-[10px] text-amber-500/60">{msg.timestamp}</span>
                    </div>
                    {parsed.title && (
                      <div className="text-[11px] font-bold text-amber-300 mb-1.5">{parsed.title}</div>
                    )}
                    {parsed.sections.map((sec, si) => (
                      <div key={si} className="mb-1.5 last:mb-0">
                        {sec.label && (
                          <div className="text-[10px] text-amber-400/50 mb-0.5">{sec.label}</div>
                        )}
                        <div className="text-[11px] text-amber-200/60 leading-relaxed">{sec.text}</div>
                      </div>
                    ))}
                    {!parsed.title && !parsed.sections.length && (
                      <div className="text-[11px] text-amber-200/60 leading-relaxed">{msg.content}</div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* 底部信息 */}
        <div className="border-t border-slate-700/20 p-3 shrink-0">
          <div className="flex items-center justify-between text-[10px] text-slate-500 mb-2">
            <span>房间 {roomInfo?.room_number || ''}</span>
            <span>{players.length}人 · {inGame ? '游戏中' : '征集中'}</span>
          </div>
          {players.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-2">
              {players.map((name) => (
                <span
                  key={name}
                  className={`rounded px-2 py-0.5 text-[10px] border ${name === roomOwner ? 'bg-amber-600/20 border-amber-500/30 text-amber-300' : 'bg-slate-700/40 border-slate-600/20 text-slate-300'}`}
                >
                  {name === roomOwner ? '👑 ' : ''}{name}
                </span>
              ))}
            </div>
          )}
          <button
            onClick={() => { playButtonSound('cancel'); leaveRoom(); }}
            className="w-full bg-red-900/30 hover:bg-red-900/50 border border-red-800/30 rounded-lg px-2 py-1.5 text-[10px] text-red-400 transition-colors"
          >
            离开房间
          </button>
        </div>
      </div>

      {/* ===== 中间：LOBBY征集面板 or 场景+字幕 ===== */}
      <div className="flex-1 flex flex-col min-w-0 relative z-10">
        {!inGame ? (
          /* ====== LOBBY 征集面板 ====== */
          <div className="flex-1 flex items-center justify-center p-6">
            <div className="w-full max-w-lg bg-slate-900/70 backdrop-blur-xl border border-slate-700/30 rounded-2xl p-8 shadow-2xl animate-[fadeSlideUp_0.5s_ease-out]">
              <div className="text-center mb-6">
                <h2
                  className="text-2xl font-serif font-bold mb-2"
                  style={{
                    background: 'linear-gradient(135deg, #93c5fd, #a78bfa)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                  }}
                >
                  灵 感 征 集
                </h2>
                <p className="text-xs text-slate-500 mb-1">请每位玩家提交世界观和角色偏好，由 AI 主持为大家定制专属剧本</p>
                <p className="text-xs text-amber-400/80 mb-2 font-bold">⚠️ 提交意向 = 报名成功，所有玩家报名后才能开始游戏</p>
              </div>

              <div className="space-y-4">
                {/* 世界观 */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-xs font-bold text-slate-400">世界观偏好</label>
                    <button
                      onClick={() => {
                        playButtonSound('dice');
                        const presets = [
                          '赛博朋克都市，霓虹灯下的阴谋',
                          '中世纪奇幻，龙与魔法的世界',
                          '废土末日，核战后的人类挣扎',
                          '东方仙侠，修真界的门派纷争',
                          '克苏鲁恐怖，不可名状的恐惧',
                          '蒸汽朋克，齿轮与魔法共存',
                          '深海探险，未知的深渊秘密',
                          '太空歌剧，星际间的政治博弈',
                          '武侠江湖，刀光剑影的恩怨',
                          '现代都市，超自然现象调查',
                        ];
                        setWorldviewPref(presets[Math.floor(Math.random() * presets.length)]);
                      }}
                      className="text-[10px] text-blue-400 hover:text-blue-300 underline"
                    >
                      🎲 随机建议
                    </button>
                  </div>
                  <textarea
                    className="w-full bg-slate-800/60 border border-slate-600/30 rounded-xl px-4 py-3 text-sm
                      focus:outline-none focus:border-blue-400/40 focus:ring-1 focus:ring-blue-500/20
                      placeholder:text-slate-600 resize-none min-h-[60px] transition-all"
                    placeholder="例如：废土朋克，克苏鲁元素..."
                    value={worldviewPref}
                    onChange={(e) => { playTypingSound(); setWorldviewPref(e.target.value); }}
                    disabled={waitingPhase}
                  />
                </div>

                {/* 角色 */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-xs font-bold text-slate-400">角色偏好</label>
                    <button
                      onClick={() => {
                        playButtonSound('dice');
                        const presets = [
                          '冷静理智的侦探',
                          '身手敏捷的盗贼',
                          '知识渊博的学者',
                          '沉默寡言的战士',
                          '巧舌如簧的商人',
                          '神秘莫测的法师',
                          '热血正义的骑士',
                          '阴险狡诈的刺客',
                          '善良温柔的医者',
                          '疯狂偏执的科学家',
                        ];
                        setRolePref(presets[Math.floor(Math.random() * presets.length)]);
                      }}
                      className="text-[10px] text-blue-400 hover:text-blue-300 underline"
                    >
                      🎲 随机建议
                    </button>
                  </div>
                  <textarea
                    className="w-full bg-slate-800/60 border border-slate-600/30 rounded-xl px-4 py-3 text-sm
                      focus:outline-none focus:border-blue-400/40 focus:ring-1 focus:ring-blue-500/20
                      placeholder:text-slate-600 resize-none min-h-[60px] transition-all"
                    placeholder="例如：男，冷酷医生..."
                    value={rolePref}
                    onChange={(e) => { playTypingSound(); setRolePref(e.target.value); }}
                    disabled={waitingPhase}
                  />
                </div>

                {/* 回合选择 */}
                <div className="flex items-center gap-3">
                  <label className="text-xs font-bold text-slate-400 shrink-0">游戏回合</label>
                  <select
                    value={totalRounds}
                    onChange={(e) => { playButtonSound('click'); setTotalRounds(Number(e.target.value)); }}
                    className="bg-slate-800/60 border border-slate-600/30 rounded-lg px-3 py-1.5 text-xs text-slate-300
                      focus:outline-none focus:border-blue-400/40"
                    disabled={waitingPhase}
                  >
                    <option value={5}>5 回合 (短)</option>
                    <option value={10}>10 回合 (中)</option>
                    <option value={15}>15 回合 (标准)</option>
                    <option value={20}>20 回合 (长)</option>
                    <option value={30}>30 回合 (超长)</option>
                  </select>
                </div>

                {/* 按钮 */}
                <div className="flex gap-3 pt-2">
                  <button
                    onClick={submitPreference}
                    className="flex-1 py-3 rounded-xl bg-blue-600/60 border border-blue-500/30
                      text-sm font-bold tracking-wider transition-all active:scale-[0.98]
                      hover:bg-blue-600/80"
                  >
                    提交意向（报名）
                  </button>
                  {currentName && roomOwner && currentName === roomOwner && (
                    <button
                      onClick={startGame}
                      className="flex-1 py-3 rounded-xl bg-emerald-600/60 border border-emerald-500/30
                        text-sm font-bold tracking-wider transition-all active:scale-[0.98]
                        hover:bg-emerald-600/80"
                    >
                      🎮 开始游戏
                    </button>
                  )}
                  {currentName && roomOwner && currentName !== roomOwner && (
                    <div className="flex-1 py-3 rounded-xl bg-slate-700/40 border border-slate-600/20
                      text-sm text-slate-500 text-center font-medium flex items-center justify-center gap-1">
                      👑 等待房主 {roomOwner} 开始...
                    </div>
                  )}
                  {(!roomOwner || players.length <= 1) && (
                    <button
                      onClick={startGame}
                      className="flex-1 py-3 rounded-xl bg-emerald-600/60 border border-emerald-500/30
                        text-sm font-bold tracking-wider transition-all active:scale-[0.98]
                        hover:bg-emerald-600/80"
                    >
                      🎮 开始游戏
                    </button>
                  )}
                </div>

                {joinError && <p className={`text-xs text-center font-bold ${joinError.startsWith('✅') ? 'text-emerald-400' : 'text-red-400'}`}>{joinError}</p>}

                {/* 已提交偏好汇总 */}
                {(suggestions.length > 0 || Object.keys(rolePrefs).length > 0) && (
                  <div className="text-[10px] text-slate-500 space-y-1 pt-2 border-t border-slate-700/30">
                    {suggestions.length > 0 && <div>世界观：{suggestions.join(' / ')}</div>}
                    {Object.keys(rolePrefs).length > 0 && (
                      <div>角色：{Object.entries(rolePrefs).map(([k, v]) => `${k}:${v}`).join(' · ')}</div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          /* ====== 游戏进行中：场景图 + 字幕条 ====== */
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* 场景名称（左上角小标签） */}
            <div className="absolute top-4 left-4 z-20">
              <div className="flex items-center gap-2">
                <span className="bg-black/40 backdrop-blur-md px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider border border-blue-500/20 text-blue-300/80">
                  {scene.name}
                </span>
                {currentRound > 0 && (
                  <span className={`bg-black/40 backdrop-blur-md px-3 py-1 rounded-full text-[10px] font-bold border text-amber-300/80 ${
                    isFinalRound ? 'border-red-500/50 animate-pulse' : 'border-amber-500/30'
                  }`}>
                    {isFinalRound ? `第${currentRound}回合（最终回合）` : `第${currentRound}回合`}
                  </span>
                )}
                {dmStatus && (
                  <span className="text-[10px] text-blue-300/50 animate-pulse">{dmStatus}</span>
                )}
              </div>
            </div>

            {/* 回合切换横幅动画 */}
            {showRoundBanner && (
              <div className={`absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 z-30 pointer-events-none animate-[roundBannerIn_0.6s_ease-out] ${
                isFinalRound ? 'animate-pulse' : ''
              }`}>
                <div className={`backdrop-blur-xl border rounded-2xl px-10 py-5 shadow-2xl ${
                  isFinalRound
                    ? 'bg-gradient-to-r from-red-900/70 via-amber-800/60 to-red-900/70 border-red-500/40 shadow-red-500/10'
                    : 'bg-gradient-to-r from-amber-900/70 via-amber-800/60 to-amber-900/70 border-amber-500/30 shadow-amber-500/10'
                }`}>
                  <div className="text-center">
                    <div className={`text-xs tracking-[0.4em] uppercase mb-1 ${
                      isFinalRound ? 'text-red-400/70' : 'text-amber-400/60'
                    }`}>
                      {isFinalRound ? 'Final Round' : 'New Round'}
                    </div>
                    <div className={`text-4xl font-black bg-clip-text text-transparent ${
                      isFinalRound
                        ? 'bg-gradient-to-r from-red-400 via-amber-300 to-red-400'
                        : 'bg-gradient-to-r from-amber-300 via-yellow-400 to-amber-300'
                    }`}>
                      第 {currentRound} 回合{isFinalRound ? '（最终回合）' : ''}
                    </div>
                    <div className="text-slate-400/70 text-xs mt-2">{scene.name}</div>
                  </div>
                </div>
              </div>
            )}

            {/* 场景描述（右上角小提示） */}
            {scene.description && scene.description !== '请创建或加入一个网页房间。' && (
              <div className="absolute top-16 right-4 z-20 max-w-xs">
                <p className="text-[11px] text-slate-400/60 italic leading-relaxed bg-black/30 backdrop-blur-sm rounded-lg px-3 py-1.5">
                  "{(scene.description || '').slice(0, 60)}{(scene.description || '').length > 60 ? '...' : ''}"
                </p>
              </div>
            )}

            {/* 线索栏（顶部中央） */}
            {inventory.length > 0 && (
              <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20">
                <div className="flex items-center gap-2 flex-wrap bg-black/40 backdrop-blur-md rounded-xl px-3 py-1.5 border border-slate-700/20">
                  <span className="text-[10px] font-bold text-slate-500 mr-1">线索</span>
                  {inventory.map((item, i) => (
                    <div
                      key={`${item.name}-${i}`}
                      className="group relative bg-amber-900/30 border border-amber-600/30 px-2 py-0.5 rounded-lg cursor-help"
                    >
                      <span className="text-amber-200 text-[10px]">{item.name}</span>
                      <div className="absolute top-full left-0 mt-2 hidden group-hover:block bg-black/90 backdrop-blur p-3 text-[11px] w-52 rounded-xl shadow-xl border border-slate-600/30 z-30">
                        {item.detail}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 中间空白区域 - 展示场景图 */}
            <div className="flex-1" />

            {/* ===== 底部字幕条 ===== */}
            <div className="shrink-0 px-4 pb-3">
              {/* DM最新消息字幕 */}
              {latestDmBody && (
                <div
                  className="max-w-2xl mx-auto bg-black/60 backdrop-blur-xl border border-slate-700/30 rounded-2xl px-6 py-4
                    animate-[subtitleSlideIn_0.4s_ease-out]"
                  style={{ animation: 'subtitleGlow 3s ease-in-out infinite' }}
                >
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400/60" />
                    <span className="text-[10px] text-amber-400/50 font-bold tracking-wider">DM 旁白</span>
                  </div>
                  <p className="text-sm text-slate-200/90 leading-relaxed whitespace-pre-wrap">
                    <TypewriterText text={latestDmBody} speed={40} />
                  </p>
                </div>
              )}

              {/* DM选项按钮 - 单选锁定 */}
              {latestDmOptions.length > 0 && (
                <div className="max-w-2xl mx-auto mt-3 space-y-1.5">
                  {latestDmOptions.map((opt, oi) => {
                    const isSelected = selectedOptionIndex === oi;
                    const isDisabled = selectedOptionIndex !== null;
                    return (
                      <button
                        key={oi}
                        onClick={() => {
                          if (isDisabled) return;
                          playButtonSound('option');
                          clearTtsQueue(); // 清空旧的TTS队列，让新内容朗读同步
                          setSelectedOptionIndex(oi);
                          setOptionGenerating(true);
                          handleSend(opt);
                        }}
                        disabled={isDisabled}
                        className={`w-full text-left px-4 py-2.5 rounded-xl
                          backdrop-blur-md text-xs transition-all group relative overflow-hidden
                          ${isSelected
                            ? 'bg-amber-900/50 border-amber-500/50 text-amber-100 cursor-default'
                            : isDisabled
                              ? 'bg-black/20 border-slate-700/10 text-slate-600 cursor-not-allowed opacity-40'
                              : 'bg-black/40 border-amber-600/20 hover:bg-amber-900/30 hover:border-amber-500/40 text-amber-200/80 cursor-pointer'
                          }`}
                        style={{ animation: `optionSlideIn 0.3s ease-out ${oi * 0.1}s both` }}
                      >
                        {/* 已选中时显示省略号动画 */}
                        {isSelected && optionGenerating && (
                          <span className="absolute right-4 top-1/2 -translate-y-1/2 text-amber-400/70 font-mono"
                            style={{ animation: 'ellipsisPulse 1s ease-in-out infinite' }}>
                            ...
                          </span>
                        )}
                        {isSelected && !optionGenerating && (
                          <span className="absolute right-4 top-1/2 -translate-y-1/2 text-emerald-400">✓</span>
                        )}
                        <span className={`${isSelected ? 'text-amber-400' : 'text-amber-500/50'} mr-2`}>
                          {isSelected ? '◆' : (isDisabled ? '○' : '▸')}
                        </span>
                        {opt}
                      </button>
                    );
                  })}
                </div>
              )}

              {/* 快捷操作按钮 */}
              <div className="max-w-2xl mx-auto mt-2 flex flex-wrap justify-center gap-1">
                {['观察', '检查物品', '商议', '前进', '搜寻', '警戒'].map((action) => (
                  <button
                    key={action}
                    onClick={() => { playButtonSound('click'); handleSend(action); }}
                    className="px-2.5 py-1 rounded-lg text-[10px]
                      bg-black/30 border border-slate-600/20
                      hover:bg-slate-700/50 hover:border-slate-500/30
                      text-slate-400 hover:text-slate-200 transition-all"
                  >
                    {action}
                  </button>
                ))}
              </div>

              {/* 自由输入框 */}
              <div className="max-w-2xl mx-auto mt-2 flex gap-2">
                <input
                  className="flex-1 bg-black/40 backdrop-blur-md border border-slate-600/30 rounded-xl px-4 py-2.5
                    text-sm focus:outline-none focus:border-blue-400/40 focus:ring-1 focus:ring-blue-500/20
                    placeholder:text-slate-600 transition-all"
                  value={inputText}
                  onChange={(e) => { playTypingSound(); setInputText(e.target.value); }}
                  onKeyDown={(e) => { if (e.key === 'Enter') { playButtonSound('click'); handleSend(); } }}
                  placeholder="输入你的行动或发言..."
                />
                <button
                  onClick={() => { playButtonSound('click'); handleSend(); }}
                  className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600/70 to-purple-600/70
                    hover:from-blue-500 hover:to-purple-500 font-bold text-xs
                    shadow-lg shadow-blue-500/20 transition-all active:scale-[0.98]"
                >
                  行动
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ===== 右侧面板切换按钮（独立于面板之外，始终可见） ===== */}
      <div
        className={`absolute top-1/2 -translate-y-1/2 z-40 transition-all duration-300 ease-in-out
          ${showRightPanel ? 'right-80' : 'right-0'}`}
      >
        <button
          onClick={() => { playButtonSound('click'); setShowRightPanel(!showRightPanel); }}
          className="bg-slate-900/60 hover:bg-slate-800/80
            border border-slate-600/20 rounded-l-xl px-2 py-6 text-slate-400 hover:text-blue-300
            transition-all backdrop-blur-md shadow-lg"
          style={{ animation: !showRightPanel ? 'arrowPulse 2s ease-in-out infinite' : 'none' }}
          title={showRightPanel ? '收起聊天' : '展开聊天'}
        >
          {showRightPanel ? '▶' : '◀'}
        </button>
      </div>

      {/* ===== 右侧面板：队伍对话 ===== */}
      <div
        className={`h-full flex flex-col shrink-0 transition-all duration-300 ease-in-out overflow-hidden
          bg-slate-900/80 backdrop-blur-xl border-l border-slate-700/20 z-20
          ${showRightPanel ? 'w-80' : 'w-0 border-l-0'}`}
      >
        <div className="px-4 py-3 border-b border-slate-700/20 shrink-0 flex items-center justify-between">
          <div>
            <div className="font-bold text-sm text-slate-300">队伍频道</div>
            <div className="text-[10px] text-slate-500 mt-0.5">
              {inGame ? '输入行动或发言' : '等待游戏开始...'}
            </div>
          </div>
          <button
            onClick={() => { playButtonSound('click'); setShowRightPanel(false); }}
            className="text-slate-500 hover:text-slate-300 transition-colors text-lg"
            title="收起聊天面板"
          >
            ✕
          </button>
        </div>

        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2.5">
          {messages.map((msg, i) => {
            const isDm = msg.user === 'DM' || msg.user === 'DM-bot';
            const isSystem = msg.user === '系统';
            const body = isDm ? stripOptions(msg.content) : msg.content;

            return (
              <div key={i} className={`flex flex-col ${isSystem ? 'items-center' : ''}`}>
                <div className="flex items-center gap-2 mb-0.5">
                  <span className={`text-[10px] ${isDm ? 'text-amber-400' : isSystem ? 'text-blue-400' : 'text-slate-400'}`}>
                    {msg.user}
                  </span>
                  <span className="text-[9px] text-slate-600">{msg.time}</span>
                </div>
                <div
                  className={`px-3 py-1.5 rounded-lg text-xs ${
                    isSystem
                      ? 'bg-transparent text-blue-400/70 italic text-center'
                      : isDm
                        ? 'bg-slate-800/60 border border-amber-700/15'
                        : 'bg-slate-800/50 border border-slate-600/20'
                  }`}
                >
                  {body && <div className="whitespace-pre-wrap leading-relaxed">{body}</div>}
                </div>
              </div>
            );
          })}
          <div ref={chatEndRef} />
        </div>

        {/* 输入区 */}
        <div className="p-3 border-t border-slate-700/20 shrink-0">
          <input
            className="w-full bg-slate-800/60 border border-slate-600/30 rounded-xl px-4 py-2.5 text-xs
              focus:outline-none focus:border-blue-400/40 focus:ring-1 focus:ring-blue-500/20
              placeholder:text-slate-600 transition-all disabled:opacity-40"
            value={inputText}
            onChange={(e) => { playTypingSound(); setInputText(e.target.value); }}
            onKeyDown={(e) => { if (e.key === 'Enter') { playButtonSound('click'); handleSend(); } }}
            placeholder={inGame ? '输入行动或发言...' : '请先创建或加入房间'}
            disabled={!inRoom}
          />
        </div>
      </div>

      {/* ===== 头像放大弹窗 ===== */}
      {showAvatarModal && playerAvatarUrl && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm avatar-modal-overlay"
          onClick={() => { playButtonSound('cancel'); setShowAvatarModal(false); }}
        >
          {/* 关闭按钮 */}
          <button
            onClick={() => { playButtonSound('cancel'); setShowAvatarModal(false); }}
            className="absolute top-6 right-6 z-10 w-10 h-10 rounded-full bg-slate-800/60 border border-slate-600/30
              flex items-center justify-center text-slate-400 hover:text-white hover:bg-red-900/40 hover:border-red-500/30
              transition-all text-lg"
            title="关闭"
          >
            ✕
          </button>

          {/* 角色名 */}
          <div className="absolute top-6 left-1/2 -translate-x-1/2 z-10">
            <span className="bg-black/50 backdrop-blur-md px-4 py-1.5 rounded-full text-sm font-bold text-blue-300 border border-blue-500/20">
              {playerCard?.role_name || '角色形象'}
            </span>
          </div>

          {/* 图片 */}
          <div className="relative max-w-[80vw] max-h-[80vh]" onClick={(e) => e.stopPropagation()}>
            <img
              src={playerAvatarUrl}
              alt={playerCard?.role_name || '角色形象'}
              className="max-w-full max-h-[80vh] object-contain rounded-2xl shadow-2xl shadow-blue-500/10"
              style={{ animation: 'avatarZoomIn 0.3s ease-out' }}
            />
            {/* 装饰边框 */}
            <div className="absolute inset-0 rounded-2xl border border-blue-400/10 pointer-events-none" />
          </div>
        </div>
      )}

      {/* ===== 结局卡片弹窗 ===== */}
      {showEndingCard && gameEnding && (
        <EndingCard
          data={gameEnding}
          onClose={() => setShowEndingCard(false)}
          onReturnToLobby={returnToLobby}
        />
      )}
    </div>
  );
}

/* ================================================================
   结局卡片组件（内联，避免额外文件）
   优先展示 AI 生成的图片，无图片时 fallback 到 CSS 卡片
   ================================================================ */
function EndingCard({ data, onClose, onReturnToLobby }) {
  const cardRef = useRef(null);
  const [saving, setSaving] = useState(false);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  const hasImage = Boolean(data.image_url);

  // 下载 AI 生成的图片（直接下载原始图片 URL）
  const handleDownloadImage = useCallback(async () => {
    if (!data.image_url) return;
    setSaving(true);
    try {
      // 通过 fetch + blob 下载，绕过跨域限制
      const response = await fetch(data.image_url);
      const blob = await response.blob();
      const link = document.createElement('a');
      link.download = `冒险回顾_${data.ending_name || '结局'}_${new Date().toISOString().slice(0, 10)}.png`;
      link.href = URL.createObjectURL(blob);
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (e) {
      console.error('下载图片失败:', e);
      // fallback: 直接打开图片链接
      window.open(data.image_url, '_blank');
    } finally {
      setSaving(false);
    }
  }, [data.image_url, data.ending_name]);

  // Fallback: html2canvas 导出 CSS 卡片
  const handleSaveJpg = useCallback(async () => {
    if (!cardRef.current) return;
    setSaving(true);
    try {
      const html2canvas = await getHtml2canvas();
      const canvas = await html2canvas(cardRef.current, {
        backgroundColor: '#1a1a2e',
        scale: 2,
        useCORS: true,
        logging: false,
      });
      const link = document.createElement('a');
      link.download = `冒险回顾_${data.ending_name || '结局'}_${new Date().toISOString().slice(0, 10)}.jpg`;
      link.href = canvas.toDataURL('image/jpeg', 0.92);
      link.click();
    } catch (e) {
      console.error('保存卡片失败:', e);
    } finally {
      setSaving(false);
    }
  }, [data.ending_name]);

  // 角色命运颜色轮换
  const fateColors = [
    { bg: 'rgba(239,68,68,0.15)', border: 'rgba(239,68,68,0.3)', text: '#fca5a5' },
    { bg: 'rgba(59,130,246,0.15)', border: 'rgba(59,130,246,0.3)', text: '#93c5fd' },
    { bg: 'rgba(16,185,129,0.15)', border: 'rgba(16,185,129,0.3)', text: '#6ee7b7' },
    { bg: 'rgba(245,158,11,0.15)', border: 'rgba(245,158,11,0.3)', text: '#fcd34d' },
    { bg: 'rgba(139,92,246,0.15)', border: 'rgba(139,92,246,0.3)', text: '#c4b5fd' },
    { bg: 'rgba(236,72,153,0.15)', border: 'rgba(236,72,153,0.3)', text: '#f9a8d4' },
  ];

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/85 backdrop-blur-md p-4"
      onClick={() => { playButtonSound('cancel'); onClose(); }}
    >
      {/* 关闭按钮 */}
      <button
        onClick={() => { playButtonSound('cancel'); onClose(); }}
        className="absolute top-6 right-6 z-10 w-10 h-10 rounded-full bg-slate-800/60 border border-slate-600/30
          flex items-center justify-center text-slate-400 hover:text-white hover:bg-red-900/40 hover:border-red-500/30
          transition-all text-lg"
        title="关闭"
      >
        ✕
      </button>

      {/* ====== AI 生成图片模式 ====== */}
      {hasImage && !imageError && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="relative flex flex-col items-center gap-4 max-h-[90vh]"
        >
          {/* 图片加载中占位 */}
          {!imageLoaded && (
            <div className="w-80 h-80 rounded-2xl bg-slate-900/80 border border-slate-700/30
              flex flex-col items-center justify-center gap-3 animate-pulse">
              <div className="w-10 h-10 border-3 border-amber-500/30 border-t-amber-400 rounded-full animate-spin" />
              <span className="text-slate-400 text-xs">AI 正在绘制结局卡片...</span>
            </div>
          )}

          {/* AI 生成的结局卡片图片 */}
          <img
            src={data.image_url}
            alt={data.ending_name || '冒险结局卡片'}
            onLoad={() => setImageLoaded(true)}
            onError={() => setImageError(true)}
            className="rounded-2xl shadow-2xl object-contain max-h-[80vh] max-w-[90vw]"
            style={{
              boxShadow: '0 0 60px rgba(251,191,36,0.15), 0 0 120px rgba(59,130,246,0.08)',
              border: '1px solid rgba(251,191,36,0.2)',
              display: imageLoaded ? 'block' : 'none',
            }}
          />

          {/* 图片加载完成后显示操作按钮 */}
          {imageLoaded && (
            <div className="flex gap-3 flex-wrap justify-center">
              <button
                onClick={() => { playButtonSound('confirm'); handleDownloadImage(); }}
                disabled={saving}
                className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-amber-600/80 to-yellow-600/80
                  hover:from-amber-500 hover:to-yellow-500 font-semibold text-sm text-white
                  shadow-lg shadow-amber-500/20 transition-all active:scale-[0.97] disabled:opacity-50
                  flex items-center gap-2"
              >
                {saving ? (
                  <>
                    <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    下载中...
                  </>
                ) : (
                  <>
                    💾 保存卡片 (PNG)
                  </>
                )}
              </button>
              <button
                onClick={() => { playButtonSound('confirm'); onReturnToLobby?.(); }}
                className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600/80 to-blue-600/80
                  hover:from-indigo-500 hover:to-blue-500 font-semibold text-sm text-white
                  shadow-lg shadow-indigo-500/20 transition-all active:scale-[0.97]
                  flex items-center gap-2"
              >
                🏠 返回大厅
              </button>
              <span className="text-slate-500 text-xs self-center">或右键图片另存为</span>
            </div>
          )}
        </div>
      )}

      {/* ====== Fallback: CSS 渲染卡片模式 ====== */}
      {(!hasImage || imageError) && (
        <div
          ref={cardRef}
          onClick={(e) => e.stopPropagation()}
          className="relative w-full max-w-lg rounded-2xl overflow-hidden shadow-2xl"
          style={{
            background: 'linear-gradient(160deg, #1a1a2e 0%, #16213e 40%, #0f3460 70%, #1a1a2e 100%)',
            border: '1px solid rgba(251,191,36,0.2)',
            boxShadow: '0 0 60px rgba(251,191,36,0.08), 0 0 120px rgba(59,130,246,0.04)',
          }}
        >
          {/* 顶部装饰线 */}
          <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-amber-500/60 via-yellow-400/80 to-amber-500/60" />

          {/* 角落装饰 */}
          <div className="absolute top-0 left-0 w-12 h-12 border-t-2 border-l-2 border-amber-400/30 rounded-tl-2xl pointer-events-none" />
          <div className="absolute top-0 right-0 w-12 h-12 border-t-2 border-r-2 border-amber-400/30 rounded-tr-2xl pointer-events-none" />
          <div className="absolute bottom-0 left-0 w-12 h-12 border-b-2 border-l-2 border-amber-400/30 rounded-bl-2xl pointer-events-none" />
          <div className="absolute bottom-0 right-0 w-12 h-12 border-b-2 border-r-2 border-amber-400/30 rounded-br-2xl pointer-events-none" />

          {/* 卡片内容 */}
          <div className="relative px-8 py-8">
            {/* 标题 */}
            <div className="text-center mb-6">
              <div className="text-amber-400/80 text-xs tracking-[0.3em] uppercase mb-2">Adventure Complete</div>
              <h1 className="text-2xl font-bold bg-gradient-to-r from-amber-300 via-yellow-400 to-amber-300 bg-clip-text text-transparent">
                📖 {data.ending_name || '冒险回顾'}
              </h1>
            </div>

            {/* 分隔线 */}
            <div className="flex items-center gap-3 mb-6">
              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-amber-500/30 to-transparent" />
              <span className="text-amber-500/60 text-lg">◆</span>
              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-amber-500/30 to-transparent" />
            </div>

            {/* 游戏信息标签 */}
            <div className="grid grid-cols-2 gap-3 mb-6">
              <InfoLabel icon="👥" label="玩家" value={(data.players || []).join('、') || '-'} />
              <InfoLabel icon="🎮" label="游戏轮次" value={data.game_rounds || '-'} />
              <InfoLabel icon="🕐" label="开始时间" value={data.game_start_time || '-'} />
              <InfoLabel icon="🏁" label="完成时间" value={data.complete_time || '-'} />
            </div>

            {/* 故事结局 */}
            <div className="mb-5">
              <div className="text-amber-400/90 text-xs font-semibold mb-2 tracking-wide">🎭 故事结局</div>
              <div className="text-slate-200 text-sm leading-relaxed bg-black/20 rounded-xl px-4 py-3 border border-white/5">
                {data.story_ending || '命运之书翻到了最后一页...'}
              </div>
            </div>

            {/* 角色命运 */}
            {data.character_fates && data.character_fates.length > 0 && (
              <div className="mb-5">
                <div className="text-amber-400/90 text-xs font-semibold mb-2 tracking-wide">🌟 角色命运</div>
                <div className="space-y-2">
                  {(data.character_fates || []).map((cf, idx) => {
                    const colors = fateColors[idx % fateColors.length];
                    return (
                      <div
                        key={idx}
                        className="flex items-start gap-3 px-3 py-2 rounded-xl text-xs"
                        style={{ backgroundColor: colors.bg, border: `1px solid ${colors.border}` }}
                      >
                        <span className="shrink-0 mt-0.5 text-base">
                          {idx === 0 ? '⚔️' : idx === 1 ? '🛡️' : idx === 2 ? '🔮' : '✨'}
                        </span>
                        <div>
                          <span className="font-semibold" style={{ color: colors.text }}>
                            {cf.role || cf.player}
                          </span>
                          {cf.player && cf.role && cf.player !== cf.role && (
                            <span className="text-slate-500 ml-1">({cf.player})</span>
                          )}
                          <div className="text-slate-300 mt-0.5">{cf.fate}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 告别语 */}
            <div className="text-center mb-6">
              <div className="inline-block bg-gradient-to-r from-amber-500/10 via-yellow-400/10 to-amber-500/10 rounded-full px-5 py-2 border border-amber-400/15">
                <span className="text-amber-300/80 text-xs italic">
                  {data.epilogue || '感谢各位玩家的精彩冒险！'}
                </span>
              </div>
            </div>

            {/* 保存按钮 */}
            <div className="flex justify-center gap-3 flex-wrap">
              <button
                onClick={() => { playButtonSound('confirm'); handleSaveJpg(); }}
                disabled={saving}
                className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-amber-600/80 to-yellow-600/80
                  hover:from-amber-500 hover:to-yellow-500 font-semibold text-xs text-white
                  shadow-lg shadow-amber-500/20 transition-all active:scale-[0.97] disabled:opacity-50
                  flex items-center gap-2"
              >
                {saving ? (
                  <>
                    <span className="inline-block w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    生成中...
                  </>
                ) : (
                  <>
                    💾 保存卡片 (JPG)
                  </>
                )}
              </button>
              <button
                onClick={() => { playButtonSound('confirm'); onReturnToLobby?.(); }}
                className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600/80 to-blue-600/80
                  hover:from-indigo-500 hover:to-blue-500 font-semibold text-xs text-white
                  shadow-lg shadow-indigo-500/20 transition-all active:scale-[0.97]
                  flex items-center gap-2"
              >
                🏠 返回大厅
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* 信息标签子组件 */
function InfoLabel({ icon, label, value }) {
  return (
    <div className="bg-black/20 rounded-xl px-3 py-2.5 border border-white/5">
      <div className="text-slate-500 text-[10px] mb-0.5">{icon} {label}</div>
      <div className="text-slate-200 text-xs font-medium truncate">{value}</div>
    </div>
  );
}
