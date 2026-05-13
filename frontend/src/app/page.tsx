"use client";

import { useState, useEffect, useRef, useCallback, Fragment } from "react";
import {
  Search, Book, ChevronRight, Send, Bot, FileText,
  Loader2, Copy, RefreshCw, BookOpen, X, Check, Plus, MessageSquare,
  PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, ChevronDown, Info
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CITATION_RE, CITATION_EXTRACT_RE, preprocessCitations, isCitationHref, extractCitationCode } from "./citations";

// Types
type Section = {
  section_id: string;
  title: string;
  score?: number;
};

type ManualGroup = {
  manual_title: string;
  results: Section[];
};

type PageData = {
  section_id: string;
  title: string;
  manual_title: string;
  text: string;
  related_pages: string[];
  gov_url: string;
  updated_at: string;
};

type SourceInfo = {
  section_id: string;
  title: string;
};

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  sources?: SourceInfo[];
  modelUsed?: string;
  timeTakenMs?: number;
  tokensUsed?: number;
};

type ChatSession = {
  id: string;
  title: string;
  messages: Message[];
  updatedAt: number;
};

type Model = {
  id: string;
  name: string;
  provider: string;
};

// Constants
const API_URL = "http://localhost:8002";

const SUGGESTIONS = [
  "Can a business claim VAT back on legal expenses for an insurance claim?",
  "What is the VAT fraction for calculating VAT on fuel scale charges?",
  "Can holding companies register for VAT?",
  "What are the rules for PAYE settlement agreements?",
];

// Helpers
let _msgIdCounter = 0;
function genId() {
  return `msg-${Date.now()}-${++_msgIdCounter}`;
}



// Main Component
export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [isChatting, setIsChatting] = useState(false);

  // History state
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    if (typeof window !== "undefined") {
      try {
        const saved = localStorage.getItem("hmrc-rag-history");
        if (saved) return JSON.parse(saved);
      } catch (e) {
        console.error("Failed to parse history", e);
      }
    }
    return [];
  });
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(true);

  // Save history to local storage when it changes
  useEffect(() => {
    localStorage.setItem("hmrc-rag-history", JSON.stringify(sessions));
  }, [sessions]);

  // Sync messages into the current session
  useEffect(() => {
    if (currentSessionId && messages.length > 0) {
      const timer = setTimeout(() => {
        setSessions(prev => prev.map(s =>
          s.id === currentSessionId ? { ...s, messages, updatedAt: Date.now() } : s
        ));
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [messages, currentSessionId]);

  const startNewChat = useCallback(() => {
    setCurrentSessionId(null);
    setMessages([]);
    setSourcePanelOpen(false);
  }, []);

  const loadSession = useCallback((id: string) => {
    const session = sessions.find(s => s.id === id);
    if (session) {
      setCurrentSessionId(id);
      setMessages(session.messages);
      setSourcePanelOpen(false);
    }
  }, [sessions]);

  const deleteSession = useCallback((id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSessions(prev => prev.filter(s => s.id !== id));
    if (currentSessionId === id) {
      startNewChat();
    }
  }, [currentSessionId, startNewChat]);

  const [models, setModels] = useState<Model[]>([]);
  const [selectedModel, setSelectedModel] = useState("qwen3.5:9b");
  const [ollamaRunning, setOllamaRunning] = useState(true);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  // Search panel
  const [searchOpen, setSearchOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Record<string, ManualGroup>>({});
  const [isSearching, setIsSearching] = useState(false);

  const [sourcePanelOpen, setSourcePanelOpen] = useState(false);
  const [activeSources, setActiveSources] = useState<SourceInfo[]>([]);
  const [activeSourcePage, setActiveSourcePage] = useState<PageData | null>(null);
  const [isLoadingSource, setIsLoadingSource] = useState(false);
  const [activeSourceId, setActiveSourceId] = useState<string | null>(null);

  // Resizer state
  const [historyWidth, setHistoryWidth] = useState(256);
  const [searchWidth, setSearchWidth] = useState(320);
  const [sourceWidth, setSourceWidth] = useState(420);
  const [isDragging, setIsDragging] = useState<"history" | "search" | "source" | null>(null);
  const [dragStart, setDragStart] = useState<{ x: number, width: number } | null>(null);
  
  const historyPanelRef = useRef<HTMLElement>(null);
  const searchPanelRef = useRef<HTMLElement>(null);
  const sourcePanelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!isDragging || !dragStart) return;

    const handleMouseMove = (e: MouseEvent) => {
      e.preventDefault();
      const delta = e.clientX - dragStart.x;

      if (isDragging === "history") {
        const newWidth = Math.max(200, Math.min(dragStart.width + delta, window.innerWidth / 2));
        if (historyPanelRef.current) historyPanelRef.current.style.width = `${newWidth}px`;
      } else if (isDragging === "search") {
        const newWidth = Math.max(250, Math.min(dragStart.width - delta, window.innerWidth / 1.5));
        if (searchPanelRef.current) searchPanelRef.current.style.width = `${newWidth}px`;
      } else if (isDragging === "source") {
        const newWidth = Math.max(300, Math.min(dragStart.width - delta, window.innerWidth / 1.5));
        if (sourcePanelRef.current) sourcePanelRef.current.style.width = `${newWidth}px`;
      }
    };

    const handleMouseUp = () => {
      if (isDragging === "history" && historyPanelRef.current) {
        setHistoryWidth(parseInt(historyPanelRef.current.style.width));
      } else if (isDragging === "search" && searchPanelRef.current) {
        setSearchWidth(parseInt(searchPanelRef.current.style.width));
      } else if (isDragging === "source" && sourcePanelRef.current) {
        setSourceWidth(parseInt(sourcePanelRef.current.style.width));
      }
      setIsDragging(null);
      setDragStart(null);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isDragging, dragStart]);

  // Copy feedback
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load models on mount
  useEffect(() => {
    fetch(`${API_URL}/models`)
      .then((res) => res.json())
      .then((data) => {
        setOllamaRunning(data.ollama_running ?? true);
        if (data.models?.length) {
          setModels(data.models);
          const saved = localStorage.getItem("rag_model");
          if (saved && data.models.find((m: Model) => m.id === saved)) {
            setSelectedModel(saved);
          } else {
            setSelectedModel(data.models[0].id);
          }
        }
      })
      .catch(console.error);
  }, []);

  // Scroll chat to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ─── Search ───────────────────────────────────────────────────────
  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setIsSearching(true);
    try {
      const res = await fetch(`${API_URL}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchQuery, limit: 15 }),
      });
      const data = await res.json();
      setSearchResults(data.groups || {});
    } catch (err) {
      console.error(err);
    } finally {
      setIsSearching(false);
    }
  };

  // Load HMRC manual page
  const loadSourcePage = useCallback(async (sectionId: string) => {
    setIsLoadingSource(true);
    setActiveSourceId(sectionId);
    setSourcePanelOpen(true);
    try {
      const res = await fetch(`${API_URL}/page?code=${sectionId}`);
      if (!res.ok) throw new Error("Failed to load");
      const data = await res.json();
      setActiveSourcePage(data);
    } catch (err) {
      console.error(err);
      setActiveSourcePage(null);
    } finally {
      setIsLoadingSource(false);
    }
  }, []);

  // Sources panel toggle
  const openSourcesPanel = useCallback((sources: SourceInfo[]) => {
    setActiveSources(sources);
    setActiveSourcePage(null);
    setActiveSourceId(null);
    setSourcePanelOpen(true);
  }, []);

  // Chat actions
  const submitChat = useCallback(async (query: string, history: Message[]) => {
    if (!query.trim() || isChatting) return;
    setChatInput("");
    setIsChatting(true);

    const startTime = Date.now();
    const modelToUse = selectedModel;

    const userMsg: Message = { id: genId(), role: "user", content: query };
    const assistantMsg: Message = { id: genId(), role: "assistant", content: "", isStreaming: true };

    const isNewSession = !currentSessionId;
    let activeSessionId = currentSessionId;
    if (isNewSession) {
      activeSessionId = genId();
      setCurrentSessionId(activeSessionId);
      const title = query.length > 30 ? query.substring(0, 30) + "..." : query;
      setSessions(prev => [{
        id: activeSessionId!,
        title,
        messages: [userMsg, assistantMsg],
        updatedAt: Date.now()
      }, ...prev]);
    }

    const newHistory = [...history, userMsg];
    setMessages([...newHistory, assistantMsg]);

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          history: history.map((m) => ({ role: m.role, content: m.content })),
          model: selectedModel,
        }),
      });

      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let fullResponse = "";
      let sources: SourceInfo[] = [];
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        // The last part might be incomplete, keep it in the buffer
        buffer = parts.pop() || "";

        let hasTokenUpdate = false;
        let isDone = false;
        let finalSources: SourceInfo[] = [];

        for (const line of parts) {
          if (!line.trim()) continue;
          try {
            const data = JSON.parse(line);
            if (data.token) {
              fullResponse += data.token;
              hasTokenUpdate = true;
            } else if (data.done) {
              finalSources = data.sources || [];
              isDone = true;
            }
          } catch {
            // JSON parse error — skip
          }
        }

        if (isDone) {
          sources = finalSources;
          const timeTakenMs = Date.now() - startTime;
          const tokensUsed = Math.ceil(fullResponse.length / 4);

          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              ...updated[updated.length - 1],
              content: fullResponse,
              isStreaming: false,
              sources,
              modelUsed: modelToUse,
              timeTakenMs,
              tokensUsed,
            };
            return updated;
          });

          if (isNewSession) {
            fetch(`${API_URL}/generate-title`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ query, response: fullResponse, model: modelToUse }),
            }).then(res => res.json()).then(data => {
              if (data.title) {
                setSessions(prev => prev.map(s =>
                  s.id === activeSessionId ? { ...s, title: data.title } : s
                ));
              }
            }).catch(console.error);
          }
        } else if (hasTokenUpdate) {
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              ...updated[updated.length - 1],
              content: fullResponse,
              isStreaming: true,
            };
            return updated;
          });
        }
      }
    } catch (err) {
      console.error(err);
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          content: "Sorry, an error occurred while processing your request.",
          isStreaming: false,
        };
        return updated;
      });
    } finally {
      setIsChatting(false);
    }
  }, [isChatting, selectedModel, currentSessionId, sessions]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submitChat(chatInput, messages);
  };

  // Regenerate response
  const regenerate = useCallback((msgId: string) => {
    setMessages((prev) => {
      // Find this assistant message and the user message before it
      const idx = prev.findIndex((m) => m.id === msgId);
      if (idx < 1) return prev;
      const userMsg = prev[idx - 1];
      if (userMsg.role !== "user") return prev;

      // Remove the last assistant message, re-send
      const history = prev.slice(0, idx - 1);
      setTimeout(() => submitChat(userMsg.content, history), 0);
      return prev.slice(0, idx - 1);
    });
  }, [submitChat]);

  // Copy to clipboard
  const copyMessage = useCallback((msgId: string, content: string) => {
    navigator.clipboard.writeText(content);
    setCopiedMsgId(msgId);
    setTimeout(() => setCopiedMsgId(null), 2000);
  }, []);

  const [showCloudWarning, setShowCloudWarning] = useState(false);

  // Model change handler
  const handleModelChange = (m: string) => {
    const selectedObj = models.find(x => x.id === m);
    if (selectedObj?.provider === "cloud" && !localStorage.getItem("cloud_warning_shown")) {
      setShowCloudWarning(true);
      localStorage.setItem("cloud_warning_shown", "true");
    }
    setSelectedModel(m);
    localStorage.setItem("rag_model", m);
  };

  // Markdown renderer with citation support
  const renderContent = useCallback((content: string) => {
    const processed = preprocessCitations(content);
    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        urlTransform={(url) => {
          if (url.startsWith("cite:")) return url;
          return url;
        }}
        components={{
          p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
          em: ({ children }) => <em className="text-foreground/80">{children}</em>,
          h1: ({ children }) => <h1 className="text-xl font-bold mb-3 mt-4 text-foreground">{children}</h1>,
          h2: ({ children }) => <h2 className="text-lg font-bold mb-2 mt-4 text-foreground">{children}</h2>,
          h3: ({ children }) => <h3 className="text-base font-semibold mb-2 mt-3 text-foreground">{children}</h3>,
          ul: ({ children }) => <ul className="list-disc list-outside ml-5 mb-3 space-y-1">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal list-outside ml-5 mb-3 space-y-1">{children}</ol>,
          li: ({ children }) => <li className="text-foreground/90">{children}</li>,
          code: ({ children, className }) => {
            const isBlock = className?.includes("language-");
            if (isBlock) {
              return <code className={`block bg-card/80 rounded-lg p-3 text-sm font-mono overflow-x-auto mb-3 ${className || ""}`}>{children}</code>;
            }
            return <code className="bg-card/80 rounded px-1.5 py-0.5 text-sm font-mono text-accent">{children}</code>;
          },
          pre: ({ children }) => <pre className="mb-3">{children}</pre>,
          blockquote: ({ children }) => <blockquote className="border-l-2 border-primary/40 pl-4 my-3 text-foreground/70 italic">{children}</blockquote>,
          table: ({ children }) => (
            <div className="overflow-x-auto mb-3 rounded-lg border border-border">
              <table className="w-full text-sm">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-card/80 border-b border-border">{children}</thead>,
          th: ({ children }) => <th className="px-3 py-2 text-left font-semibold text-foreground text-xs uppercase tracking-wider">{children}</th>,
          td: ({ children }) => <td className="px-3 py-2 border-t border-border/50 text-foreground/80">{children}</td>,
          hr: () => <hr className="my-4 border-border/50" />,
          // Citation links: intercept cite: URLs and render as interactive buttons
          a: ({ children, href }) => {
            if (isCitationHref(href)) {
              const code = extractCitationCode(href)!;
              return (
                <button
                  onClick={(e) => { e.preventDefault(); loadSourcePage(code); }}
                  className="citation-btn"
                  type="button"
                >
                  {code}
                </button>
              );
            }
            return <a href={href} target="_blank" rel="noreferrer" className="text-primary hover:text-accent underline underline-offset-2 transition-colors">{children}</a>;
          },
        }}
      >
        {processed}
      </ReactMarkdown>
    );
  }, [loadSourcePage]);

  // Main Render
  return (
    <div className="flex h-screen overflow-hidden bg-background">

      {/* History Panel */}
      {historyOpen && (
        <aside
          ref={historyPanelRef}
          className="relative flex-shrink-0 border-r border-border flex flex-col bg-card/20 animate-slide-in-left"
          style={{ width: historyWidth }}
        >
          <div
            onMouseDown={(e) => {
              setIsDragging("history");
              setDragStart({ x: e.clientX, width: historyWidth });
            }}
            className="absolute top-0 right-[-3px] w-1.5 h-full cursor-col-resize hover:bg-primary/50 transition-colors z-50"
          />
          <div className="p-4 border-b border-border flex items-center justify-between">
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <MessageSquare size={15} className="text-primary" />
              Chat History
            </h2>
            <button
              onClick={() => setHistoryOpen(false)}
              className="action-btn"
              title="Close history"
            >
              <PanelLeftClose size={16} />
            </button>
          </div>
          <div className="p-3">
            <button
              onClick={startNewChat}
              className="w-full py-2 bg-primary/10 text-primary border border-primary/20 rounded-lg text-sm font-medium hover:bg-primary/20 transition-colors flex items-center justify-center gap-2"
            >
              <Plus size={16} /> New Chat
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {sessions.map((s) => (
              <div
                key={s.id}
                onClick={() => loadSession(s.id)}
                className={`group relative px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${currentSessionId === s.id
                  ? "bg-secondary/80 text-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-secondary/40 hover:text-foreground"
                  }`}
              >
                <div className="text-sm truncate pr-6">{s.title}</div>
                <button
                  onClick={(e) => deleteSession(s.id, e)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 hover:text-red-500 transition-opacity p-1"
                  title="Delete chat"
                >
                  <X size={14} />
                </button>
              </div>
            ))}
            {sessions.length === 0 && (
              <div className="text-center text-xs text-muted-foreground/50 mt-8 px-4">
                No past chats yet.
              </div>
            )}
          </div>
        </aside>
      )}

      {/* Chat View */}
      <main className="flex-1 flex flex-col min-w-0 relative">

        {/* Cloud Warning Modal */}
        {showCloudWarning && (
          <div className="absolute inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm animate-fade-in">
            <div className="bg-card border border-border p-6 rounded-2xl max-w-sm w-full shadow-2xl mx-4">
              <h3 className="text-lg font-bold text-foreground mb-2">Cloud Model Selected</h3>
              <p className="text-sm text-muted-foreground mb-6 leading-relaxed">
                You selected a cloud model. These powerful hosted models require a free Ollama account to work properly.
                Please ensure you have signed up at <a href="https://ollama.com" target="_blank" rel="noreferrer" className="text-primary hover:underline">ollama.com</a>
                and then run <code>ollama login</code> in your terminal. <br /><br />
              </p>
              <div className="flex justify-end">
                <button
                  onClick={() => setShowCloudWarning(false)}
                  className="bg-primary text-primary-foreground px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
                >
                  Got it
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Ollama Offline Banner */}
        {!ollamaRunning && (
          <div className="bg-destructive/10 text-destructive text-xs font-medium py-1.5 px-4 text-center border-b border-destructive/20 flex items-center justify-center gap-2">
            <Bot size={14} />
            Ollama is not currently running. Local models will not respond.
          </div>
        )}

        {/* Top bar */}
        <header className="flex items-center justify-between px-5 py-2.5 border-b border-border bg-card/30 flex-shrink-0">
          <div className="flex items-center gap-3">
            {!historyOpen && (
              <button
                onClick={() => setHistoryOpen(true)}
                className="action-btn"
                title="Open history"
              >
                <PanelLeftOpen size={16} />
              </button>
            )}
            <div className="flex items-center gap-2">
              <img src="/logo.svg" alt="Logo" className="w-8 h-8" />
              <h1 className="text-base font-semibold text-foreground">
                HMRC Tax Assistant
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div
              className="relative outline-none"
              tabIndex={0}
              onBlur={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                  setDropdownOpen(false);
                }
              }}
            >
              <button
                type="button"
                onClick={() => setDropdownOpen(!dropdownOpen)}
                className="flex items-center justify-between w-52 bg-secondary/60 text-xs text-muted-foreground border border-border rounded-lg pl-3 pr-3 py-1.5 cursor-pointer hover:bg-secondary transition-colors focus:outline-none focus:ring-1 focus:ring-primary/40"
              >
                <span className="truncate pr-2 text-foreground font-medium">
                  {models.find(m => m.id === selectedModel)?.name || "Select Model"}
                </span>
                <div className="flex items-center gap-1.5 flex-shrink-0 text-muted-foreground">
                  {models.find(m => m.id === selectedModel)?.provider === 'cloud' && <span>☁️</span>}
                  <ChevronDown size={12} className={`transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
                </div>
              </button>

              {dropdownOpen && (
                <div className="absolute top-full right-0 mt-1.5 w-56 bg-card border border-border rounded-xl shadow-xl overflow-hidden z-50 animate-in fade-in zoom-in-95 duration-100">
                  <div className="max-h-60 overflow-y-auto p-1">
                    {models.map((m, index) => {
                      const showSeparator = index > 0 && m.provider === 'cloud' && models[index - 1].provider !== 'cloud';
                      return (
                        <Fragment key={m.id}>
                          {showSeparator && <div className="h-px bg-border my-1 mx-2" />}
                          <button
                            type="button"
                            onClick={() => {
                              handleModelChange(m.id);
                              setDropdownOpen(false);
                            }}
                            className={`w-full flex items-center justify-between px-3 py-2 text-xs text-left rounded-md transition-colors ${selectedModel === m.id
                              ? 'bg-primary/10 text-primary font-medium'
                              : 'text-foreground hover:bg-secondary/80'
                              }`}
                          >
                            <span className="truncate">{m.name}</span>
                            {m.provider === 'cloud' && <span className="flex-shrink-0 ml-2 opacity-80">☁️</span>}
                          </button>
                        </Fragment>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {!searchOpen && (
              <button
                onClick={() => setSearchOpen(true)}
                className="action-btn"
                title="Open search manuals"
              >
                <Search size={16} />
              </button>
            )}
          </div>
        </header>

        {/* Messages area */}
        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full px-6 animate-fade-in">
              <div className="mb-8 text-center">
                <h2 className="text-3xl font-bold text-foreground mb-2">
                  Ask about UK tax legislation
                </h2>
                <p className="text-muted-foreground mt-2 max-w-sm mx-auto">
                  Tax assistance grounded in legislation
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl w-full">
                {SUGGESTIONS.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      setChatInput(s);
                      setTimeout(() => submitChat(s, []), 0);
                    }}
                    className="suggestion-chip text-left"
                  >
                    <ChevronRight size={14} className="inline mr-1.5 text-primary/50" />
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto px-5 py-6 space-y-8">
              {messages.map((msg) => (
                <div key={msg.id} className="animate-fade-in">
                  {msg.role === "user" ? (
                    <div className="flex justify-end">
                      <div className="bg-primary/12 border border-primary/15 text-foreground px-5 py-3 rounded-2xl rounded-tr-md max-w-[80%]">
                        <p className="text-[15px] leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {/* Avatar row */}
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-full bg-primary/15 flex items-center justify-center border border-primary/20">
                          <Bot size={13} className="text-primary" />
                        </div>
                        <span className="text-xs font-medium text-muted-foreground">Tax Assistant</span>
                      </div>

                      {/* Response text */}
                      <div className="pl-8">
                        {(() => {
                          let displayContent = msg.content;
                          let extractedSuggestions: string[] = [];

                          const suggestionMatch = displayContent.match(/<suggestions>([\s\S]*?)(?:<\/suggestions>|$)/i);
                          if (suggestionMatch) {
                            // Strip from display content so user doesn't see the raw tags
                            displayContent = displayContent.replace(/<suggestions>[\s\S]*?(?:<\/suggestions>|$)/ig, '').trim();

                            if (!msg.isStreaming && suggestionMatch[1]) {
                              extractedSuggestions = suggestionMatch[1]
                                .replace(/<\/suggestions>/ig, '')
                                .split('|')
                                .map(s => s.trim())
                                .filter(Boolean);
                            }
                          }

                          return (
                            <>
                              <div className="text-[15px] leading-[1.75] text-foreground/90">
                                {renderContent(displayContent)}
                                {msg.isStreaming && (
                                  <span className="inline-block w-1.5 h-4 ml-0.5 bg-primary/60 animate-pulse align-middle rounded-sm" />
                                )}
                              </div>

                              {/* Action bar */}
                              {!msg.isStreaming && msg.content && (
                                <div className="flex items-center gap-1 mt-3 pt-2">
                                  {/* Info */}
                                  <div className="relative group flex items-center justify-center">
                                    <button className="action-btn cursor-default" title="Generation info" type="button">
                                      <Info size={15} />
                                    </button>
                                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 bg-card border border-border p-3 rounded-lg shadow-xl text-xs text-muted-foreground opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50 pointer-events-none">
                                      <div className="space-y-1.5">
                                        <div className="flex justify-between"><span>Model:</span> <span className="text-foreground font-medium truncate ml-2">{msg.modelUsed || "Unknown"}</span></div>
                                        <div className="flex justify-between"><span>Time:</span> <span className="text-foreground font-medium">{msg.timeTakenMs ? (msg.timeTakenMs / 1000).toFixed(1) + "s" : "-"}</span></div>
                                        <div className="flex justify-between"><span>Tokens:</span> <span className="text-foreground font-medium">{msg.tokensUsed ? "~" + msg.tokensUsed : "-"}</span></div>
                                      </div>
                                    </div>
                                  </div>

                                  {/* Copy */}
                                  <button
                                    onClick={() => copyMessage(msg.id, displayContent)}
                                    className="action-btn"
                                    title="Copy response"
                                  >
                                    {copiedMsgId === msg.id ? <Check size={15} className="text-success" /> : <Copy size={15} />}
                                  </button>

                                  {/* Regenerate */}
                                  <button
                                    onClick={() => regenerate(msg.id)}
                                    className="action-btn"
                                    title="Regenerate response"
                                  >
                                    <RefreshCw size={15} />
                                  </button>

                                  {/* Sources */}
                                  {msg.sources && msg.sources.length > 0 && (
                                    <button
                                      onClick={() => openSourcesPanel(msg.sources!)}
                                      className="ml-2 inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-border bg-secondary/40 text-xs text-muted-foreground hover:text-foreground hover:border-primary/30 hover:bg-secondary/70 transition-all duration-200"
                                      title="View sources"
                                    >
                                      <BookOpen size={13} />
                                      Sources ({msg.sources.length})
                                    </button>
                                  )}
                                </div>
                              )}

                              {/* Follow-up Suggestions */}
                              {extractedSuggestions.length > 0 && (
                                <div className="flex flex-wrap gap-2 mt-4 pt-2 border-t border-border/50">
                                  {extractedSuggestions.map((sug, i) => (
                                    <button
                                      key={i}
                                      onClick={() => {
                                        setChatInput('');
                                        submitChat(sug, messages);
                                      }}
                                      className="suggestion-chip !py-1.5 !px-3 !text-xs"
                                    >
                                      {sug}
                                    </button>
                                  ))}
                                </div>
                              )}
                            </>
                          );
                        })()}
                      </div>
                    </div>
                  )}
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>
          )}
        </div>

        {/* Input */}
        <div className="px-4 pb-4 pt-2 bg-background flex-shrink-0">
          <form onSubmit={handleSubmit} className="max-w-3xl mx-auto relative">
            <input
              ref={inputRef}
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Ask a tax question..."
              className="w-full bg-card border border-border rounded-2xl pl-5 pr-14 py-3.5 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/40 placeholder:text-muted-foreground/40 shadow-lg shadow-black/20 transition-all duration-200"
              disabled={isChatting}
            />
            <button
              type="submit"
              disabled={!chatInput.trim() || isChatting}
              className="absolute right-2 top-1/2 -translate-y-1/2 w-9 h-9 flex items-center justify-center rounded-xl bg-primary text-white disabled:opacity-30 hover:bg-primary/80 transition-all duration-150"
            >
              {isChatting ? <Loader2 size={17} className="animate-spin" /> : <Send size={17} />}
            </button>
          </form>
          <p className="text-center text-[11px] text-muted-foreground/40 mt-2">
            Answers are AI-generated from HMRC manuals. Always verify with the original source.
          </p>
        </div>
      </main>

      {/* Sources Panel */}
      {sourcePanelOpen && (
        <aside
          ref={sourcePanelRef}
          className="relative flex-shrink-0 border-l border-border flex flex-col bg-card/50 animate-slide-in-right"
          style={{ width: sourceWidth }}
        >
          <div
            onMouseDown={(e) => {
              setIsDragging("source");
              setDragStart({ x: e.clientX, width: sourceWidth });
            }}
            className="absolute top-0 left-[-3px] w-1.5 h-full cursor-col-resize hover:bg-primary/50 transition-colors z-50"
          />
          {/* Header */}
          <div className="p-4 border-b border-border flex items-center justify-between flex-shrink-0">
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <BookOpen size={15} className="text-primary" />
              {activeSourcePage ? activeSourcePage.section_id : "Sources"}
            </h2>
            <div className="flex items-center gap-1">
              {activeSourcePage && (
                <button
                  onClick={() => { setActiveSourcePage(null); setActiveSourceId(null); }}
                  className="action-btn text-xs flex items-center gap-1"
                  title="Back to sources list"
                >
                  <ChevronRight size={14} className="rotate-180" />
                  <span className="text-[11px]">Back</span>
                </button>
              )}
              <button
                onClick={() => { setSourcePanelOpen(false); setActiveSourcePage(null); setActiveSourceId(null); }}
                className="action-btn"
                title="Close"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto">
            {isLoadingSource ? (
              <div className="flex items-center justify-center h-40">
                <Loader2 className="text-primary animate-spin" size={24} />
              </div>
            ) : activeSourcePage ? (
              <div className="p-5 animate-fade-in">
                <div className="mb-5 pb-4 border-b border-border">
                  <div className="text-xs text-muted-foreground/70 flex items-center gap-1.5 mb-2">
                    <Book size={12} />
                    {activeSourcePage.manual_title}
                  </div>
                  <h3 className="text-lg font-bold text-foreground mb-2">{activeSourcePage.title}</h3>
                  <div className="flex items-center gap-3">
                    <span className="bg-primary/15 text-primary px-2 py-0.5 rounded text-xs font-bold font-mono">
                      {activeSourcePage.section_id}
                    </span>
                    <a
                      href={activeSourcePage.gov_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[11px] text-muted-foreground/60 hover:text-primary transition-colors underline underline-offset-2"
                    >
                      View on GOV.UK
                    </a>
                  </div>
                </div>

                <div className="space-y-3">
                  {activeSourcePage.text.split("\n\n").map((paragraph, i) => (
                    <p key={i} className="text-sm leading-relaxed text-card-foreground/80">
                      {paragraph}
                    </p>
                  ))}
                </div>

                {activeSourcePage.related_pages.length > 0 && (
                  <div className="mt-8 pt-4 border-t border-border">
                    <h4 className="text-xs font-semibold text-muted-foreground mb-2">Cross References</h4>
                    <div className="flex flex-wrap gap-1.5">
                      {activeSourcePage.related_pages.slice(0, 15).map((code) => (
                        <button
                          key={code}
                          onClick={() => loadSourcePage(code)}
                          className="bg-secondary/50 hover:bg-primary/15 text-foreground/70 hover:text-primary px-2 py-1 rounded text-xs font-mono transition-colors border border-border"
                        >
                          {code}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              /* ── Sources list ── */
              <div className="p-4 space-y-2 animate-fade-in">
                {activeSources.length === 0 ? (
                  <p className="text-sm text-muted-foreground/50 text-center mt-8">No sources available.</p>
                ) : (
                  activeSources.map((src, i) => (
                    <button
                      key={`${src.section_id}-${i}`}
                      onClick={() => loadSourcePage(src.section_id)}
                      className={`w-full text-left p-3.5 rounded-xl border transition-all duration-150 group ${activeSourceId === src.section_id
                        ? "border-primary/30 bg-primary/8"
                        : "border-border bg-card/60 hover:border-primary/20 hover:bg-card"
                        }`}
                    >
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="bg-primary/15 text-primary px-1.5 py-0.5 rounded text-[10px] font-bold font-mono">
                          {src.section_id}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground group-hover:text-foreground/80 transition-colors line-clamp-2">
                        {src.title}
                      </p>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
        </aside>
      )}

      {/* Search Panel */}
      {searchOpen && (
        <aside
          ref={searchPanelRef}
          className="relative flex-shrink-0 border-l border-border flex flex-col bg-card/40 animate-slide-in-right"
          style={{ width: searchWidth }}
        >
          <div
            onMouseDown={(e) => {
              setIsDragging("search");
              setDragStart({ x: e.clientX, width: searchWidth });
            }}
            className="absolute top-0 left-[-3px] w-1.5 h-full cursor-col-resize hover:bg-primary/50 transition-colors z-50"
          />
          {/* Header */}
          <div className="p-4 border-b border-border flex items-center justify-between">
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Search size={15} className="text-primary" />
              Search Manuals
            </h2>
            <button
              onClick={() => setSearchOpen(false)}
              className="action-btn"
              title="Close search"
            >
              <PanelRightClose size={16} />
            </button>
          </div>

          {/* Search input */}
          <div className="p-3 border-b border-border">
            <form onSubmit={handleSearch} className="relative">
              <input
                type="text"
                placeholder="e.g. VIT13500, fuel scale charges..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-background border border-border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 placeholder:text-muted-foreground/50"
              />
              <Search className="absolute left-2.5 top-2.5 text-muted-foreground/50" size={15} />
              {isSearching && (
                <Loader2 className="absolute right-2.5 top-2.5 text-primary animate-spin" size={15} />
              )}
            </form>
          </div>

          {/* Results */}
          <div className="flex-1 overflow-y-auto p-3 space-y-5">
            {Object.keys(searchResults).length === 0 && !isSearching && (
              <div className="text-center text-muted-foreground/50 text-xs mt-8 px-4">
                <Book size={28} className="mx-auto mb-3 opacity-30" />
                <p>Search for section codes or topics across all HMRC manuals.</p>
              </div>
            )}

            {Object.entries(searchResults).map(([slug, group]) => (
              <div key={slug} className="space-y-1.5">
                <h3 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70 flex items-center gap-1.5 px-1">
                  <FileText size={11} />
                  {group.manual_title}
                </h3>
                <div className="space-y-0.5 ml-1 border-l border-border/40 pl-2">
                  {group.results.map((res) => (
                    <button
                      key={res.section_id}
                      onClick={() => loadSourcePage(res.section_id)}
                      className="w-full text-left px-2.5 py-2 rounded-md hover:bg-secondary/60 transition-colors text-sm group"
                    >
                      <div className="font-mono text-xs text-primary/80 group-hover:text-primary transition-colors">
                        {res.section_id}
                      </div>
                      <div className="text-xs text-muted-foreground/70 line-clamp-1 mt-0.5">
                        {res.title}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </aside>
      )}
    </div>
  );
}
