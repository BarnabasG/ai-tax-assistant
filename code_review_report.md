# Code Review: HMRC Tax Assistant

Here is a comprehensive code review covering `frontend/src/app/page.tsx` and `backend/api.py` based on the guidelines in the `code-review-excellence` skill.

## 🟡 [important] Blocking I/O in Async Endpoints (FastAPI)
**File:** `backend/api.py`

**Issue:** Several endpoints (`/page`, `/search`, `/manual-tree`) are defined with `async def` but call synchronous/blocking functions (like `store.get_by_section_id`, `parse_section`, `store.hybrid_search`). 

**Why it matters:** In FastAPI, `async def` endpoints run on the main event loop thread. If a blocking operation is executed inside them, it will freeze the entire event loop, preventing the server from handling any other concurrent requests (like your streaming `/chat` endpoint!).

**Suggestion:** Change these endpoints from `async def` to `def`. FastAPI will automatically run synchronous `def` endpoints in a threadpool, keeping your event loop unblocked.

```python
# Before
@app.get("/page")
async def get_page(code: str): ...

# After
@app.get("/page")
def get_page(code: str): ...
```

## 🟡 [important] State Thrashing on Mouse Drag (React)
**File:** `frontend/src/app/page.tsx`

**Issue:** The panel resizing logic updates React state (`setHistoryWidth`, `setSourceWidth`) on every single `mousemove` event.

**Why it matters:** Updating state triggers a full re-render of the `Home` component. Since `Home` contains heavy components like `ReactMarkdown`, firing a full re-render every few milliseconds during a mouse drag will cause severe UI lag and jank.

**Suggestion:** For high-frequency events like drag-to-resize, use a `useRef` to target the DOM node and update `style.width` directly during `mousemove`, and only `setState` on `mouseup`.

## 🟡 [important] LocalStorage Data Wipe Race Condition
**File:** `frontend/src/app/page.tsx`

**Issue:** The initialization of `sessions` from `localStorage` uses two independent `useEffect` hooks:
```typescript
// Load
useEffect(() => { ... setSessions(parsed) ... }, []);

// Save
useEffect(() => { localStorage.setItem("hmrc-rag-history", JSON.stringify(sessions)); }, [sessions]);
```

**Why it matters:** On initial mount, `sessions` is initialized to `[]`. The second effect immediately fires and saves `[]` to `localStorage`. While it usually gets overwritten quickly when the first effect calls `setSessions(parsed)`, this is a dangerous race condition. If an error occurs or the user closes the tab at the exact wrong moment, you risk wiping out their entire chat history.

**Suggestion:** Initialize `sessions` lazily in the `useState` call instead:
```typescript
const [sessions, setSessions] = useState<ChatSession[]>(() => {
  if (typeof window !== "undefined") {
    try {
      const saved = localStorage.getItem("hmrc-rag-history");
      if (saved) return JSON.parse(saved);
    } catch (e) {}
  }
  return [];
});

// Now you only need the save effect!
```

## 🟢 [nit] Hardcoded Title Generation Model
**File:** `backend/api.py`

**Issue:** In `/generate-title`, the model string `"gemma3:12b-cloud"` is hardcoded.

**Suggestion:** If this model goes offline or is renamed, the title generation will fail silently to the fallback. Consider passing the `modelToUse` from the frontend, or reading it from an environment variable.

## 💡 [suggestion] ReactMarkdown Re-rendering
**File:** `frontend/src/app/page.tsx`

**Issue:** During chat streaming, the `renderContent` function re-parses the entire markdown payload on every token update. 

**Suggestion:** While this works for short responses, for long legal documents, this can bottleneck the main thread. You might consider throttling the token state updates (e.g., update state every 50ms instead of every token) or using a lighter markdown renderer for the active stream, switching to `react-markdown` once the stream is complete.

## 🎉 [praise] Great Component Architecture
**Overall:** The streaming logic with the token buffer and robust split is handled beautifully. The fallback mechanism for local cache and graceful error handling on fetch stream interruption is well-implemented. Great work on integrating the custom citation handling and the clean UI architecture!
