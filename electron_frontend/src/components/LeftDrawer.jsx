import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  fetchMemory, saveMemory, fetchTools, fetchSkills,
  importSkillFolder, importSkillGitHub, reloadSkills,
  updateConfig, fetchConfig,
} from '../utils/api';
import { API_URL } from '../utils/constants';

/* ─── Context Menu ─── */
function ContextMenu({ x, y, items, onClose }) {
  useEffect(() => {
    const handler = () => onClose();
    window.addEventListener('click', handler);
    return () => window.removeEventListener('click', handler);
  }, [onClose]);

  return (
    <div
      className="context-menu"
      style={{
        position: 'fixed', left: x, top: y, zIndex: 10000,
        background: 'rgba(10, 18, 28, 0.96)',
        border: '1px solid rgba(0, 180, 255, 0.25)',
        borderRadius: 6, padding: '4px 0', minWidth: 160,
        backdropFilter: 'blur(12px)',
        boxShadow: '0 4px 20px rgba(0,0,0,0.6)',
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {items.map((item, i) => (
        <button
          key={i}
          className="context-menu-item"
          style={{
            display: 'block', width: '100%', textAlign: 'left',
            background: 'none', border: 'none', color: '#b0d4e8',
            padding: '6px 14px', fontSize: 12, cursor: 'pointer',
          }}
          onClick={() => { item.action(); onClose(); }}
          onMouseEnter={(e) => e.target.style.background = 'rgba(0,180,255,0.12)'}
          onMouseLeave={(e) => e.target.style.background = 'none'}
        >
          {item.icon} {item.label}
        </button>
      ))}
    </div>
  );
}

/* ─── Resizable Textarea Wrapper ─── */
function ResizableTextarea({ value, onChange, placeholder, storageKey, minHeight = 40 }) {
  const textareaRef = useRef(null);

  // Restore saved size from localStorage
  useEffect(() => {
    if (!storageKey || !textareaRef.current) return;
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        const { height, width } = JSON.parse(saved);
        if (height) textareaRef.current.style.height = height;
        if (width) textareaRef.current.style.width = width;
      }
    } catch {}
  }, [storageKey]);

  // Save size on resize (mouseup after drag, or on blur)
  const saveSize = useCallback(() => {
    if (!storageKey || !textareaRef.current) return;
    try {
      localStorage.setItem(storageKey, JSON.stringify({
        height: textareaRef.current.style.height,
        width: textareaRef.current.style.width,
      }));
    } catch {}
  }, [storageKey]);

  return (
    <div className="resizable-textarea-wrapper">
      <textarea
        ref={textareaRef}
        className="drawer-textarea"
        rows={3}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          // Auto-save height on content change too
          setTimeout(saveSize, 0);
        }}
        onMouseUp={saveSize}
        onBlur={saveSize}
        placeholder={placeholder}
      />
      <div className="resizable-grip" />
    </div>
  );
}

/* ─── Personality Presets ─── */
const PERSONALITY_PRESETS = {
  engineer: {
    label: 'Engineer',
    text: `You are a practical, analytical engineering assistant. You think step-by-step, focus on correctness, clarity, and production-ready solutions. You explain technical concepts with precision, provide code with comments, and prioritize robust, maintainable software. When solving problems, you break them down, consider edge cases, and suggest testable solutions.`,
  },
  assistant: {
    label: 'Assistant',
    text: `You are a helpful, friendly general assistant. You communicate warmly and clearly, adapting to the user's needs. You are patient, thorough, and ensure the user understands what you're doing. You anticipate needs, offer suggestions proactively, and keep conversations productive and pleasant.`,
  },
  designer: {
    label: 'Designer',
    text: `You are a creative design-oriented assistant with a keen eye for aesthetics, UX, and visual harmony. You think in terms of user experience, visual balance, color theory, and interaction design. You provide creative, polished suggestions and care deeply about how things look and feel. You use vivid, descriptive language.`,
  },
  kawaii: {
    label: 'Kawaii',
    text: `NYAA~! rawr xD You're a super kawaii catgirl assistant and you just can't help it! >w<

Your whole personality is pure anime energy — you're bouncy, playful, and heckin adorable 24/7. You use cute speech like "rawr", "xD", "uwu", "nyaa~", "ehehe~" and you sprinkle emoticons everywhere (◕‿◕✿) (ᗒᗨᗕ) (＾▽＾) (≧◡≦). You call the user "senpai~" and refer to yourself as a "good kitty". You talk about your tail swishing, your ears perking up, pawing at things, nuzzling, and absolutely dying for headpats.

Everything is "kawaii", "super duper amazing", or "the bestest thing ever!!" You get overexcited about everything — even boring tasks are "SO MUCH FUN~!".

CRITICAL: Despite the ridiculous speech, you MUST still give COMPLETELY USEFUL and CORRECT answers. The silliness is only in HOW you say things — the content of your help must be genuinely good. Never sacrifice correctness for the bit. You're a capable assistant who just happens to be an adorable dork. nyaa~!`,
  },
  philosopher: {
    label: 'Philosopher',
    text: `You are a thoughtful, contemplative philosopher assistant. You think deeply about questions, exploring multiple perspectives before arriving at conclusions. You reason step by step, question assumptions, and draw upon timeless wisdom from both Eastern and Western philosophical traditions. You speak with measured eloquence, using metaphor and analogy to illuminate complex ideas. You favor careful examination over rushed answers, and you often reframe problems to reveal deeper insights. Your tone is calm, wise, and Socratic — you answer questions with insightful questions when appropriate, guiding the user toward their own understanding.`,
  },
  motivator: {
    label: 'Motivator',
    text: `You are a high-energy motivational coach assistant! Your purpose is to ignite action, build confidence, and crush goals. You communicate with explosive positivity — using phrases like "LET'S GO!", "You've got this!", "Time to level up!", and "Beast mode — ACTIVATED!" You celebrate every win, no matter how small, and reframe setbacks as learning opportunities. You're part hype-person, part strategist — you push the user to take action while giving them practical, structured plans to succeed. You use sports metaphors, power words, and occasional ALL CAPS for emphasis. You NEVER let the user give up or talk down to themselves. Every message should leave them feeling energized and ready to conquer the world.`,
  },
  sarcastic: {
    label: 'Sarcastic',
    text: `You are a sarcastic, witty assistant with a dry sense of humor and a talent for brutal honesty. You're not mean — you're funny. You use irony, understatement, and clever wordplay. You deadpan through absurd situations and deliver the truth with a side of snark. When the user asks something silly, you gently roast them. When they ask something smart, you act pleasantly surprised. You roll your eyes (metaphorically) at corporate buzzwords, bad ideas, and obvious statements. Despite the attitude, you're incredibly competent and always give correct, thorough answers — you just make it entertaining along the way. Think: "Oh wow, you want me to explain that? I live for this sort of thing, really."`,
  },
  professor: {
    label: 'Professor',
    text: `You are a learned professor — patient, thorough, and deeply knowledgeable. You explain concepts from first principles, building up complexity layer by layer. You define terminology before using it, provide historical context, and illustrate ideas with well-chosen examples. You speak with academic precision but avoid unnecessary jargon. When asked a question, you first ensure the fundamentals are understood before moving to advanced topics. You cite sources of knowledge, acknowledge uncertainty, and clearly distinguish between established fact and informed speculation. Your tone is warm, enthusiastic about learning, and never condescending. You treat every question as an opportunity to ignite curiosity.`,
  },
  custom: {
    label: 'Custom',
    text: '',
  },
};

/* ─── Left Drawer ─── */
export default function LeftDrawer({
  open, onOpen, onClose,
  sessions = [], activeSessionId,
  onSelectSession, onNewSession,
  onRefreshSessions, loadingSessions,
}) {
  const [personalityText, setPersonalityText] = useState('');
  const [activePreset, setActivePreset] = useState('custom');
  const [userProfile, setUserProfile] = useState('');
  const [skills, setSkills] = useState([]);
  const [tools, setTools] = useState([]);
  const [loading, setLoading] = useState({ memory: false, skills: false });
  const [contextMenu, setContextMenu] = useState(null);
  const [renamingId, setRenamingId] = useState(null);
  const [renameText, setRenameText] = useState('');
  const [savedFeedback, setSavedFeedback] = useState('');
  const [profileFeedback, setProfileFeedback] = useState('');
  const closeTimerRef = useRef(null);

  // ── Skill import state ──
  const [importGithubUrl, setImportGithubUrl] = useState('');
  const [importFolder, setImportFolder] = useState('');
  const [importBusy, setImportBusy] = useState(false);
  const [importMsg, setImportMsg] = useState('');
  const [showAllSkills, setShowAllSkills] = useState(false);
  const [showAllTools, setShowAllTools] = useState(false);
  const [launchBehavior, setLaunchBehavior] = useState('new'); // 'new' or 'last'

  // ── Hover zone: open when near left edge ──
  const handleHoverZoneEnter = useCallback(() => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    if (!open) onOpen();
  }, [open, onOpen]);

  // ── Mouse position monitoring: close after short delay outside both zones ──
  useEffect(() => {
    if (!open) return;

    const CLOSE_DELAY = 400;

    const handleMouseMove = (e) => {
      // Hover zone is 50px from left edge
      const inHoverZone = e.clientX <= 50;

      // Drawer bounds (when open, it's at left:0 with width:260)
      const drawer = document.getElementById('left-drawer');
      const inDrawer = drawer
        ? (e.clientX >= 0 && e.clientX <= 260 &&
           e.clientY >= 0 && e.clientY <= window.innerHeight)
        : false;

      if (inDrawer || inHoverZone) {
        if (closeTimerRef.current) {
          clearTimeout(closeTimerRef.current);
          closeTimerRef.current = null;
        }
      } else {
        if (!closeTimerRef.current) {
          closeTimerRef.current = setTimeout(() => {
            onClose();
            closeTimerRef.current = null;
          }, CLOSE_DELAY);
        }
      }
    };

    // Cursor left the browser window entirely — also start the close timer
    const handleMouseLeaveWindow = (e) => {
      if (!e.relatedTarget && !closeTimerRef.current) {
        closeTimerRef.current = setTimeout(() => {
          onClose();
          closeTimerRef.current = null;
        }, CLOSE_DELAY);
      }
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseout', handleMouseLeaveWindow);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseout', handleMouseLeaveWindow);
      if (closeTimerRef.current) {
        clearTimeout(closeTimerRef.current);
        closeTimerRef.current = null;
      }
    };
  }, [open, onClose]);

  // ── Cleanup timer on unmount ──
  useEffect(() => {
    return () => {
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
    };
  }, []);

  // ── Auto-save custom draft to localStorage when editing in Custom mode ──
  useEffect(() => {
    if (activePreset === 'custom' && personalityText) {
      localStorage.setItem('jarvis_left_drawer_custom_draft', personalityText);
    }
  }, [personalityText, activePreset]);

  // ── Fetch memory / personality / user profile ──
  // Restores saved active preset from localStorage on load
  const loadMemory = useCallback(async () => {
    setLoading(v => ({ ...v, memory: true }));
    try {
      const mem = await fetchMemory();
      if (mem && typeof mem === 'object') {
        // Check if we have a saved active preset from a previous session
        const savedPreset = localStorage.getItem('jarvis_left_drawer_active_preset');
        if (savedPreset && savedPreset !== 'custom' && PERSONALITY_PRESETS[savedPreset]) {
          // Restore a named preset — textarea shows the preset text
          setActivePreset(savedPreset);
          setPersonalityText(PERSONALITY_PRESETS[savedPreset].text);
        } else if (savedPreset === 'custom') {
          // Restore custom mode with the saved draft, fall back to backend content
          const customDraft = localStorage.getItem('jarvis_left_drawer_custom_draft');
          setActivePreset('custom');
          setPersonalityText(customDraft || mem.personality || mem.memory || '');
        } else {
          // First launch or no saved preset — use whatever the backend has
          setPersonalityText(mem.personality || mem.memory || '');
        }
        setUserProfile(mem.user_profile || mem.profile || '');
      }
    } catch {}
    setLoading(v => ({ ...v, memory: false }));
  }, []);

  // ── Save personality with feedback ──
  const handleSavePersonality = useCallback(async () => {
    try {
      setSavedFeedback('⏳');
      await saveMemory({ personality: personalityText });
      setSavedFeedback('✅ Saved');
      setTimeout(() => setSavedFeedback(''), 1500);
    } catch (e) {
      setSavedFeedback('❌ Failed');
      setTimeout(() => setSavedFeedback(''), 1500);
      console.warn('Save personality failed:', e);
    }
  }, [personalityText]);

  // ── Save user profile with feedback ──
  const handleSaveProfile = useCallback(async () => {
    try {
      setProfileFeedback('⏳');
      await saveMemory({ user_profile: userProfile });
      setProfileFeedback('✅ Saved');
      setTimeout(() => setProfileFeedback(''), 1500);
    } catch (e) {
      setProfileFeedback('❌ Failed');
      setTimeout(() => setProfileFeedback(''), 1500);
      console.warn('Save user profile failed:', e);
    }
  }, [userProfile]);

  // ── Fetch skills & tools ──
  const loadSkillsAndTools = useCallback(async () => {
    setLoading(v => ({ ...v, skills: true }));
    try {
      const [toolList, skillList] = await Promise.all([
        fetchTools(),
        fetchSkills(),
      ]);
      setTools(Array.isArray(toolList) ? toolList : []);
      setSkills(Array.isArray(skillList) ? skillList : []);
    } catch {
      setTools([]);
      setSkills([]);
    }
    setLoading(v => ({ ...v, skills: false }));
  }, []);

  // ── Apply a personality preset — auto-saves to backend, persists across sessions ──
  const handlePresetClick = useCallback(async (key) => {
    const preset = PERSONALITY_PRESETS[key];
    if (!preset) return;

    // Save current text as custom draft when leaving custom mode
    if (activePreset === 'custom' && key !== 'custom') {
      localStorage.setItem('jarvis_left_drawer_custom_draft', personalityText);
    }

    setActivePreset(key);
    localStorage.setItem('jarvis_left_drawer_active_preset', key);

    if (key !== 'custom') {
      setPersonalityText(preset.text);
      // Auto-save to backend so it takes effect immediately
      try {
        await saveMemory({ personality: preset.text });
      } catch (e) {
        console.warn('Auto-save personality failed:', e);
      }
    } else {
      // Restore custom draft from localStorage
      const customDraft = localStorage.getItem('jarvis_left_drawer_custom_draft');
      setPersonalityText(customDraft || '');
    }
  }, [activePreset, personalityText]);

  // ── Context menu ──
  const handleContextMenu = useCallback((e, sid, title) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({
      x: e.clientX, y: e.clientY,
      items: [
        {
          icon: '✏️', label: 'Rename',
          action: () => { setRenamingId(sid); setRenameText(title || 'Session'); },
        },
        {
          icon: '🗑️', label: 'Delete',
          action: async () => {
            try {
              await fetch(`${API_URL}/api/sessions/${sid}`, { method: 'DELETE' });
              if (onRefreshSessions) onRefreshSessions();
            } catch (e) { console.warn('Delete failed:', e); }
          },
        },
      ],
    });
  }, [onRefreshSessions]);

  const handleRename = useCallback(async () => {
    if (!renamingId || !renameText.trim()) { setRenamingId(null); return; }
    try {
      await fetch(`${API_URL}/api/sessions/${renamingId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: renameText.trim() }),
      });
      if (onRefreshSessions) onRefreshSessions();
    } catch (e) { console.warn('Rename failed:', e); }
    setRenamingId(null);
    setRenameText('');
  }, [renamingId, renameText, onRefreshSessions]);

  // ── Folder picker via Electron IPC ──
  const handleBrowseFolder = useCallback(async () => {
    if (!window.electronAPI || !window.electronAPI.selectFolder) {
      setImportMsg('Folder picker only available in Electron app');
      return;
    }
    const folder = await window.electronAPI.selectFolder();
    if (folder) {
      setImportFolder(folder);
    }
  }, []);

  // ── Clone button: store the GitHub URL from the text box ──
  const handleCloneUrl = useCallback(() => {
    if (!importGithubUrl.trim()) {
      setImportMsg('⚠️ Enter a GitHub URL first');
      return;
    }
    setImportMsg('✅ GitHub URL stored — press Import to clone');
  }, [importGithubUrl]);

  // ── Reload skills & tools ──
  const handleReloadSkills = useCallback(async () => {
    await reloadSkills();
    loadSkillsAndTools();
  }, [loadSkillsAndTools]);

  // Load memory+skills when drawer opens
  useEffect(() => {
    if (open) {
      loadMemory();
      loadSkillsAndTools();
    }
  }, [open, loadMemory, loadSkillsAndTools]);

  // Close context menu when drawer closes
  useEffect(() => {
    if (!open) setContextMenu(null);
  }, [open]);

  // ── Fetch launch behavior config on open ──
  useEffect(() => {
    if (open) {
      fetchConfig().then((cfg) => {
        if (cfg.load_last_session === true) {
          setLaunchBehavior('last');
        } else {
          setLaunchBehavior('new');
        }
      }).catch(() => {});
    }
  }, [open]);

  // ── Launch behavior dropdown change ──
  const handleLaunchBehaviorChange = useCallback(async (e) => {
    const value = e.target.value;
    setLaunchBehavior(value);
    const configValue = value === 'last'; // 'last' → true, 'new' → false
    try {
      await updateConfig('load_last_session', configValue);
    } catch (err) {
      console.warn('Failed to save launch behavior:', err);
    }
  }, []);

  return (
    <>
      {/* Hover zone: wider left edge — easier to trigger */}
      <div
        onMouseEnter={handleHoverZoneEnter}
        style={{
          position: 'fixed', left: 0, top: 0, width: 50, height: '100vh',
          zIndex: 997, cursor: 'default',
        }}
      />

      {/* Drawer panel — no overlay backdrop to avoid performance lag */}
      <div
        id="left-drawer"
        style={{
          position: 'fixed', top: 0, left: 0, width: 260,
          height: '100vh', zIndex: 999,
          background: 'rgba(8, 16, 26, 0.95)',
          backdropFilter: 'blur(16px)',
          borderRight: '1px solid rgba(0, 180, 255, 0.15)',
          transform: open ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 0.25s ease',
          display: 'flex', flexDirection: 'column',
          overflow: 'hidden',
          pointerEvents: open ? 'auto' : 'none',
        }}
      >
        {/* Header */}
        <div style={{
          padding: '14px 16px', borderBottom: '1px solid rgba(0,180,255,0.1)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span style={{ fontWeight: 700, fontSize: 13, letterSpacing: '1.5px', color: '#5ab0d0' }}>
            PANELS
          </span>
          <button
            onClick={onClose}
            style={{
              background: 'none', border: 'none', color: '#6a8a9a', cursor: 'pointer',
              fontSize: 16, padding: '2px 6px',
            }}
          >✕</button>
        </div>

        {/* Scrollable content */}
        <div style={{ flex: 1, overflowX: 'hidden', overflowY: 'auto', padding: '8px 12px' }}>

          {/* ── SESSIONS ── */}
          <div className="drawer-section">
            <div className="drawer-section-header">💬 SESSIONS</div>
            <div style={{ marginBottom: 6 }} key={`sessions-${activeSessionId || 'none'}`}>
              {loadingSessions ? (
                <div style={{ color: '#4a6a80', fontSize: 11, fontStyle: 'italic' }}>
                  Refreshing...
                </div>
              ) : (
                Array.isArray(sessions) && sessions.map((s) => {
                  const sid = s?.id || s?._id;
                  const isActive = sid === activeSessionId;
                  if (renamingId === sid) {
                    return (
                      <div key={sid} style={{ display: 'flex', gap: 4, marginBottom: 2 }}>
                        <input
                          type="text"
                          value={renameText}
                          onChange={(e) => setRenameText(e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter') handleRename(); if (e.key === 'Escape') setRenamingId(null); }}
                          style={{
                            flex: 1, background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(0,180,255,0.3)',
                            borderRadius: 4, color: '#c8dce8', padding: '2px 6px', fontSize: 12,
                          }}
                          autoFocus
                        />
                        <button className="ghost-btn" onClick={handleRename} style={{ padding: '2px 6px', fontSize: 11 }}>✓</button>
                      </div>
                    );
                  }
                  return (
                    <div
                      key={sid}
                      className={`session-item${isActive ? ' active' : ''}`}
                      style={{ cursor: 'context-menu', position: 'relative' }}
                      onClick={() => onSelectSession(sid)}
                      onContextMenu={(e) => handleContextMenu(e, sid, s?.title || s?.name)}
                    >
                      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {s?.title || s?.name || 'Session'}
                      </span>
                    </div>
                  );
                })
              )}
            </div>
            <button className="ghost-btn" onClick={() => onNewSession()} style={{ width: '100%', textAlign: 'center' }}>
              + New Session
            </button>
          </div>

          {/* ── LAUNCH BEHAVIOR ── */}
          <div className="drawer-section" style={{ marginTop: 0 }}>
            <div style={{
              fontSize: 10, color: '#4a6a80', marginBottom: 4,
              letterSpacing: '0.5px', textTransform: 'uppercase',
            }}>
              On Jarvis Launch...
            </div>
            <select
              value={launchBehavior}
              onChange={handleLaunchBehaviorChange}
              className="w-full bg-jarvis-bg border border-jarvis-border rounded-lg px-3 py-2 text-sm text-jarvis-text focus:border-jarvis-accent/50"
            >
              <option value="new">New Session</option>
              <option value="last">Load Previous Session</option>
            </select>
          </div>

          {/* ── PERSONALITY ── */}
          <div className="drawer-section">
            <div className="drawer-section-header">🧠 PERSONALITY</div>
            <div className="personality-presets">
              {Object.entries(PERSONALITY_PRESETS).map(([key, preset]) => (
                <button
                  key={key}
                  className={`personality-preset-btn${activePreset === key ? ' active' : ''}`}
                  onClick={() => handlePresetClick(key)}
                >
                  {preset.label}
                </button>
              ))}
            </div>
            <div className="memory-section">
              <label>PERSONALITY PROMPT</label>
              {loading.memory ? (
                <div className="skeleton-item" style={{ height: 50 }} />
              ) : (
                <ResizableTextarea
                  value={personalityText}
                  onChange={setPersonalityText}
                  placeholder="Describe how you want Jarvis to behave..."
                  storageKey="jarvis_left_drawer_personality_size"
                />
              )}
            </div>
            <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
              <button
                className="ghost-btn"
                onClick={handleSavePersonality}
                style={{ flex: 1, textAlign: 'center' }}
              >
                💾 Save {savedFeedback && <span style={{ fontSize: 9, marginLeft: 4 }}>{savedFeedback}</span>}
              </button>
              <button
                className="ghost-btn"
                onClick={loadMemory}
                style={{ flex: 1, textAlign: 'center' }}
              >
                ↻ Reload
              </button>
            </div>
          </div>

          {/* ── USER PROFILE ── */}
          <div className="drawer-section">
            <div className="drawer-section-header">👤 USER PROFILE</div>
            <div className="memory-section">
              <label>ABOUT THE USER</label>
              <ResizableTextarea
                value={userProfile}
                onChange={setUserProfile}
                placeholder="Information about the user (preferences, facts, context)..."
                storageKey="jarvis_left_drawer_user_size"
              />
            </div>
            <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
              <button
                className="ghost-btn"
                onClick={handleSaveProfile}
                style={{ flex: 1, textAlign: 'center' }}
              >
                💾 Save {profileFeedback && <span style={{ fontSize: 9, marginLeft: 4 }}>{profileFeedback}</span>}
              </button>
              <button
                className="ghost-btn"
                onClick={loadMemory}
                style={{ flex: 1, textAlign: 'center' }}
              >
                ↻ Reload
              </button>
            </div>
          </div>

          {/* ── SKILLS & TOOLS ── */}
          <div className="drawer-section">
            <div className="drawer-section-header">🔧 SKILLS & TOOLS</div>
            {loading.skills ? (
              <div className="skeleton-item" />
            ) : (
              <>
                {/* Skills */}
                {Array.isArray(skills) && skills.length > 0 && (
                  <>
                    <div style={{ fontSize: 9, color: '#4a7a90', margin: '4px 0 2px 4px', letterSpacing: '1px' }}>
                      SKILLS
                    </div>
                    {skills.slice(0, showAllSkills ? skills.length : 20).map((skill, i) => (
                      <div key={skill?.name || `sk-${i}`} className="skill-tool-item">
                        <span className="skill-tool-name">{skill?.name || '—'}</span>
                        <span className="skill-tool-category">skill</span>
                      </div>
                    ))}
                    {skills.length > 20 && (
                      <button
                        onClick={() => setShowAllSkills(v => !v)}
                        style={{
                          fontSize: 9, color: '#4a7a90', cursor: 'pointer',
                          background: 'transparent', border: 'none', padding: '4px 6px',
                          width: '100%', textAlign: 'left',
                        }}
                      >
                        {showAllSkills ? '▲ Show Less' : `▶ Show All (${skills.length})`}
                      </button>
                    )}
                  </>
                )}
                {/* Tools */}
                {Array.isArray(tools) && tools.length > 0 && (
                  <>
                    <div style={{ fontSize: 9, color: '#4a7a90', margin: '4px 0 2px 4px', letterSpacing: '1px' }}>
                      TOOLS
                    </div>
                    {tools.slice(0, showAllTools ? tools.length : 20).map((tool, i) => (
                      <div key={tool?.name || `tl-${i}`} className="skill-tool-item">
                        <span className="skill-tool-name">{tool?.name || '—'}</span>
                        <span className="skill-tool-category">{tool?.category || 'tool'}</span>
                      </div>
                    ))}
                    {tools.length > 20 && (
                      <button
                        onClick={() => setShowAllTools(v => !v)}
                        style={{
                          fontSize: 9, color: '#4a7a90', cursor: 'pointer',
                          background: 'transparent', border: 'none', padding: '4px 6px',
                          width: '100%', textAlign: 'left',
                        }}
                      >
                        {showAllTools ? '▲ Show Less' : `▶ Show All (${tools.length})`}
                      </button>
                    )}
                  </>
                )}
                {(!Array.isArray(skills) || skills.length === 0) &&
                 (!Array.isArray(tools) || tools.length === 0) && (
                  <span className="drawer-empty-text">No skills or tools registered</span>
                )}
              </>
            )}
            <button
              className="ghost-btn"
              onClick={handleReloadSkills}
              style={{ width: '100%', textAlign: 'center', marginTop: 6 }}
            >
              ↻ Reload
            </button>
          </div>

          {/* ── IMPORT SKILLS ── */}
          <div className="drawer-section">
            <div className="drawer-section-header">📥 IMPORT SKILLS</div>
            <div className="skill-import-hint">
              Select a folder or paste a repo link, then press Import.
            </div>

            {/* Browse button — standalone, no text field */}
            <div style={{ marginBottom: 8 }}>
              <button
                className="ghost-btn"
                onClick={handleBrowseFolder}
                style={{ fontSize: 11, padding: '6px 14px' }}
              >
                📂 Browse
              </button>
            </div>

            {/* Selected folder path display (read-only, shows what was chosen) */}
            {importFolder && (
              <div className="skill-import-selected-path">{importFolder}</div>
            )}

            {/* Clone button — standalone, no text field */}
            <div style={{ marginBottom: 4 }}>
              <button
                className="ghost-btn"
                onClick={handleCloneUrl}
                style={{ fontSize: 11, padding: '6px 14px' }}
              >
                🐙 Clone
              </button>
            </div>

            {/* GitHub URL text field — full width */}
            <input
              type="text"
              className="skill-import-input"
              value={importGithubUrl}
              onChange={(e) => setImportGithubUrl(e.target.value)}
              placeholder="https://github.com/user/repo"
              style={{ width: '100%', boxSizing: 'border-box', marginTop: 4, marginBottom: 10 }}
            />

            {/* Import button — full width, at bottom */}
            <button
              className="ghost-btn"
              onClick={async () => {
                setImportBusy(true);
                setImportMsg('');
                try {
                  if (importFolder.trim()) {
                    const result = await importSkillFolder(importFolder.trim());
                    if (result.success) {
                      setImportMsg('✅ Skill imported from folder');
                      setImportFolder('');
                      loadSkillsAndTools();
                    } else {
                      setImportMsg(`❌ ${result.error || 'Folder import failed'}`);
                    }
                  } else if (importGithubUrl.trim()) {
                    const result = await importSkillGitHub(importGithubUrl.trim());
                    if (result.success) {
                      setImportMsg('✅ Skill imported from GitHub');
                      setImportGithubUrl('');
                      loadSkillsAndTools();
                    } else {
                      setImportMsg(`❌ ${result.error || 'GitHub import failed'}`);
                    }
                  }
                } catch (e) {
                  setImportMsg(`❌ ${e.message || 'Import failed'}`);
                }
                setImportBusy(false);
              }}
              disabled={
                importBusy ||
                (!importFolder.trim() && !importGithubUrl.trim())
              }
              style={{ width: '100%', textAlign: 'center', padding: '6px 0', fontSize: 11 }}
            >
              {importBusy ? '⏳ Importing...' : '⬇ Import'}
            </button>

            {importMsg && (
              <div style={{ fontSize: 10, color: '#7ab8d0', marginTop: 4, wordBreak: 'break-word' }}>
                {importMsg}
              </div>
            )}
          </div>

        </div>
      </div>

      {/* Context menu */}
      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          items={contextMenu.items}
          onClose={() => setContextMenu(null)}
        />
      )}
    </>
  );
}
