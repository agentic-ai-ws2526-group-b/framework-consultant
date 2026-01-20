"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Select,
  SelectTrigger,
  SelectContent,
  SelectItem,
  SelectValue,
} from "@/components/ui/select"

type FrameworkRec = {
  framework: string
  score: number // 0..1
  description?: string
  match_reason?: string
  pros?: string[]
  cons?: string[]
  recommendation?: string
  url?: string
  match_percent?: number
  score_breakdown?: any
}

type AgentRec = {
  title: string
  summary: string
  score: number // 0..1
  match_percent?: number
  score_breakdown?: any
  metadata?: Record<string, any>
}

type BoschUseCase = {
  title: string
  summary: string
  score: number
  match_percent?: number
  score_breakdown?: any
  metadata?: Record<string, any>
}

type Phase = "form" | "bosch" | "frameworks" | "selectedUseCase"
type Mode = "template" | "chat"

type ChatRole = "assistant" | "user"

type ChatMessage = {
  id: string
  role: ChatRole
  content: string
  meta?: {
    kind?: "results_agents" | "results_frameworks"
    agents?: AgentRec[]
    frameworks?: FrameworkRec[]
  }
}

type ChatStep =
  | "intro"
  | "agentType"
  | "priorities"
  | "experience"
  | "learning"
  | "useCase"
  | "confirm"
  | "running"
  | "results"

const PRIORITY_OPTIONS = [
  { key: "speed", label: "Schnell & leichtgewichtig ⚡" },
  { key: "tools", label: "Viele Integrationen / Tools 🔌" },
  { key: "memory", label: "Gute Gedächtnisfunktionen 🧠" },
  { key: "rag", label: "Dokumenten-Suche (RAG) 📄" },
  { key: "privacy", label: "Datenschutzfreundlich 🔒" },
  { key: "multi", label: "Multi-Agent-Fähig 🤖" },
] as const

const AGENT_TYPES = [
  "Chatbot",
  "Daten-Agent",
  "Workflow-Agent",
  "Analyse-Agent",
  "Multi-Agent-System",
  "unknown",
] as const

const EXPERIENCE_LEVELS = [
  { value: "beginner", label: "Anfänger" },
  { value: "intermediate", label: "Fortgeschritten" },
  { value: "expert", label: "Experte" },
] as const

const LEARNING_PREFS = [
  { value: "learn", label: "Etwas dazu lernen" },
  { value: "simple", label: "Einfache Lösung" },
] as const

function uid() {
  return Math.random().toString(16).slice(2) + Date.now().toString(16)
}

function pct(score01: number | undefined) {
  const s = typeof score01 === "number" ? score01 : 0
  return Math.max(0, Math.min(100, Math.round(s * 100)))
}

export default function Home() {
  // ---------------------------
  // Global mode
  // ---------------------------
  const [mode, setMode] = useState<Mode>("template")

  // ---------------------------
  // Template/Form state
  // ---------------------------
  const [agentType, setAgentType] = useState("")
  const [useCase, setUseCase] = useState("")
  const [experienceLevel, setExperienceLevel] = useState("")
  const [learningPreference, setLearningPreference] = useState("")
  const [priorities, setPriorities] = useState<string[]>([])

  // ---------------------------
  // Results state (template flow)
  // ---------------------------
  const [phase, setPhase] = useState<Phase>("form")
  const [loading, setLoading] = useState(false)
  const [boschUseCases, setBoschUseCases] = useState<BoschUseCase[]>([])
  const [selectedBosch, setSelectedBosch] = useState<BoschUseCase | null>(null)
  const [frameworkResults, setFrameworkResults] = useState<FrameworkRec[]>([])
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // ---------------------------
  // Chat state
  // ---------------------------
  const [chatStep, setChatStep] = useState<ChatStep>("intro")
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatInput, setChatInput] = useState("")

  // Chat-collected answers
  const [chatAgentType, setChatAgentType] = useState<string>("")
  const [chatPriorities, setChatPriorities] = useState<string[]>([])
  const [chatExperience, setChatExperience] = useState<string>("")
  const [chatLearning, setChatLearning] = useState<string>("")
  const [chatUseCase, setChatUseCase] = useState<string>("")

  const chatEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [chatMessages.length, mode])

  // ---------------------------
  // Payload builders
  // ---------------------------
  const formPayload = useMemo(() => {
    return {
      agent_type: agentType,
      priorities,
      use_case: useCase,
      experience_level: experienceLevel,
      learning_preference: learningPreference,
    }
  }, [agentType, priorities, useCase, experienceLevel, learningPreference])

  const chatPayload = useMemo(() => {
    return {
      agent_type: chatAgentType,
      priorities: chatPriorities,
      use_case: chatUseCase,
      experience_level: chatExperience,
      learning_preference: chatLearning,
    }
  }, [chatAgentType, chatPriorities, chatUseCase, chatExperience, chatLearning])

  // ---------------------------
  // Common helpers
  // ---------------------------
  const togglePriority = (key: string) => {
    setPriorities((prev) => (prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key]))
  }

  const canSubmit = Boolean(agentType && useCase && experienceLevel && learningPreference)

  const resetAllTemplate = () => {
    setPhase("form")
    setLoading(false)
    setErrorMsg(null)
    setBoschUseCases([])
    setSelectedBosch(null)
    setFrameworkResults([])
  }

  const resetChat = () => {
    setChatStep("intro")
    setChatMessages([])
    setChatInput("")
    setChatAgentType("")
    setChatPriorities([])
    setChatExperience("")
    setChatLearning("")
    setChatUseCase("")
  }

  // ---------------------------
  // API calls (template flow)
  // ---------------------------
  const fetchBoschUseCases = async () => {
    setLoading(true)
    setErrorMsg(null)
    setBoschUseCases([])
    setFrameworkResults([])
    setSelectedBosch(null)

    try {
      const res = await fetch("/api/use-cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formPayload),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || data?.error || "Fehler beim Laden der Bosch Use Cases.")

      const list: BoschUseCase[] = Array.isArray(data?.use_cases) ? data.use_cases : []
      setBoschUseCases(list)

      if (list.length > 0 && data?.suggest_show_frameworks === false) {
        setPhase("bosch")
      } else {
        setPhase("frameworks")
        await fetchFrameworks(true)
      }
    } catch (e: any) {
      setErrorMsg(String(e?.message || e))
      setPhase("form")
    } finally {
      setLoading(false)
    }
  }

  const fetchFrameworks = async (force_frameworks: boolean) => {
    setLoading(true)
    setErrorMsg(null)
    setFrameworkResults([])

    try {
      const payload = { ...formPayload, force_frameworks }

      const res = await fetch("/api/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || data?.error || "Fehler beim Laden der Frameworks.")

      let parsed: any = null
      try {
        parsed = JSON.parse(data?.answer ?? "{}")
      } catch {
        parsed = null
      }

      const recs: FrameworkRec[] = Array.isArray(parsed?.framework_recommendations)
        ? parsed.framework_recommendations
        : []

      setFrameworkResults(recs)
    } catch (e: any) {
      setErrorMsg(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }

  // ---------------------------
  // Chat message helpers
  // ---------------------------
  const pushAssistant = (content: string, meta?: ChatMessage["meta"]) => {
    setChatMessages((prev) => [...prev, { id: uid(), role: "assistant", content, meta }])
  }
  const pushUser = (content: string) => {
    setChatMessages((prev) => [...prev, { id: uid(), role: "user", content }])
  }

  const startChat = () => {
    resetChat()
    setChatStep("agentType")
    pushAssistant(
      "Hi! Ich begleite dich Schritt für Schritt. Wir bauen gemeinsam deine Anfrage und ich zeige dir dann passende Bosch-Use-Cases und/oder Frameworks.\n\nAls erstes: **Was soll dein Agent tun?**"
    )
  }

  const toggleChatPriority = (key: string) => {
    setChatPriorities((prev) => (prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key]))
  }

  const summarizeChatAnswers = () => {
    const prioText = chatPriorities.length ? chatPriorities.join(", ") : "keine"
    return (
      `Bitte kurz prüfen:\n\n` +
      `• Agententyp: ${chatAgentType || "—"}\n` +
      `• Prioritäten: ${prioText}\n` +
      `• Erfahrungslevel: ${chatExperience || "—"}\n` +
      `• Lernpräferenz: ${chatLearning || "—"}\n` +
      `• Use Case: ${chatUseCase ? `"${chatUseCase.slice(0, 120)}${chatUseCase.length > 120 ? "…" : ""}"` : "—"}\n\n` +
      `Soll ich damit die Empfehlungen berechnen?`
    )
  }

  // ---------------------------
  // Chat API flow (same logic, just chat)
  // ---------------------------
  const chatRunFlow = async () => {
    // Step -> running
    setChatStep("running")
    pushAssistant("Alles klar — ich berechne jetzt passende Empfehlungen…")

    try {
      // 1) use-cases
      const resUC = await fetch("/api/use-cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(chatPayload),
      })
      const dataUC = await resUC.json()
      if (!resUC.ok) throw new Error(dataUC?.detail || dataUC?.error || "Fehler beim Laden der Use Cases.")

      const useCases: AgentRec[] = Array.isArray(dataUC?.use_cases) ? dataUC.use_cases : []
      const suggestFrameworks = Boolean(dataUC?.suggest_show_frameworks)

      if (useCases.length > 0 && suggestFrameworks === false) {
        pushAssistant(
          "Ich habe passende **Bosch Use Cases (Agenten)** gefunden. Du kannst einen auswählen oder alternativ Frameworks anzeigen lassen.",
          { kind: "results_agents", agents: useCases }
        )
        pushAssistant("Möchtest du **Frameworks statt Agenten** sehen? (Ja/Nein)")
        setChatStep("results")
        return
      }

      // 2) else frameworks forced
      const resAg = await fetch("/api/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...chatPayload, force_frameworks: true }),
      })
      const dataAg = await resAg.json()
      if (!resAg.ok) throw new Error(dataAg?.detail || dataAg?.error || "Fehler beim Laden der Frameworks.")

      let parsed: any = null
      try {
        parsed = JSON.parse(dataAg?.answer ?? "{}")
      } catch {
        parsed = null
      }

      const frameworks: FrameworkRec[] = Array.isArray(parsed?.framework_recommendations)
        ? parsed.framework_recommendations
        : []

      if (!frameworks.length) {
        pushAssistant("Ich habe leider keine Framework-Empfehlungen erhalten. Prüfe bitte Backend-Konsole & Response.")
      } else {
        pushAssistant("Hier sind die **Framework-Empfehlungen** basierend auf deinen Antworten:", {
          kind: "results_frameworks",
          frameworks,
        })
      }

      setChatStep("results")
    } catch (e: any) {
      pushAssistant(`❌ Fehler: ${String(e?.message || e)}`)
      setChatStep("results")
    }
  }

  // ---------------------------
  // Chat submit handling
  // ---------------------------
  const onChatSubmit = async () => {
    const input = chatInput.trim()
    if (!input) return

    pushUser(input)
    setChatInput("")

    // interpret per step
    if (chatStep === "agentType") {
      // Allow free input but map roughly
      const norm = input.toLowerCase()
      const picked =
        AGENT_TYPES.find((t) => t.toLowerCase() === norm) ||
        (norm.includes("chat") ? "Chatbot" : "") ||
        (norm.includes("workflow") ? "Workflow-Agent" : "") ||
        (norm.includes("multi") ? "Multi-Agent-System" : "") ||
        (norm.includes("analyse") ? "Analyse-Agent" : "") ||
        (norm.includes("daten") ? "Daten-Agent" : "") ||
        ""

      if (!picked) {
        pushAssistant("Ich konnte das noch nicht zuordnen. Bitte wähle einen Agententyp (z.B. **Chatbot**, **Workflow-Agent**, **Multi-Agent-System**).")
        return
      }

      setChatAgentType(picked)
      pushAssistant(`Okay: **${picked}**.\n\nAls nächstes: **Was ist dir wichtig?** Wähle beliebig viele Prioritäten. (Du kannst auch „weiter“ schreiben, wenn du fertig bist.)`)
      setChatStep("priorities")
      return
    }

    if (chatStep === "priorities") {
      const norm = input.toLowerCase()

      if (["weiter", "fertig", "ok", "done", "next"].includes(norm)) {
        pushAssistant("Alles klar.\n\nWie gut schätzt du dich im Erstellen von Agenten ein? (**beginner**, **intermediate**, **expert**)")
        setChatStep("experience")
        return
      }

      // allow user to type keys or words
      const matched: string[] = []
      for (const opt of PRIORITY_OPTIONS) {
        if (norm.includes(opt.key) || norm.includes(opt.label.toLowerCase().split(" ")[0])) {
          matched.push(opt.key)
        }
      }

      if (!matched.length) {
        pushAssistant("Du kannst Prioritäten nennen wie: **rag**, **tools**, **speed**, **memory**, **privacy**, **multi** — oder „weiter“.")
        return
      }

      // toggle matched
      setChatPriorities((prev) => {
        let next = [...prev]
        for (const m of matched) {
          next = next.includes(m) ? next.filter((x) => x !== m) : [...next, m]
        }
        return next
      })

      pushAssistant(`Notiert. Aktuell ausgewählt: ${chatPriorities.length ? chatPriorities.join(", ") : "—"}\nWenn du fertig bist, schreibe **weiter**.`)
      return
    }

    if (chatStep === "experience") {
      const norm = input.toLowerCase()
      const allowed = ["beginner", "intermediate", "expert"]
      if (!allowed.includes(norm)) {
        pushAssistant("Bitte antworte mit **beginner**, **intermediate** oder **expert**.")
        return
      }
      setChatExperience(norm)
      pushAssistant("Super.\n\nWillst du **etwas dazu lernen** oder eine **einfache Lösung**? Antworte mit **learn** oder **simple**.")
      setChatStep("learning")
      return
    }

    if (chatStep === "learning") {
      const norm = input.toLowerCase()
      if (!["learn", "simple"].includes(norm)) {
        pushAssistant("Bitte antworte mit **learn** oder **simple**.")
        return
      }
      setChatLearning(norm)
      pushAssistant("Perfekt.\n\nJetzt beschreibe bitte deinen **Use Case** in 1–3 Sätzen. Was soll der Agent konkret machen?")
      setChatStep("useCase")
      return
    }

    if (chatStep === "useCase") {
      setChatUseCase(input)
      pushAssistant(summarizeChatAnswers())
      pushAssistant("Antworte mit **ja** zum Starten oder **nein** zum Ändern.")
      setChatStep("confirm")
      return
    }

    if (chatStep === "confirm") {
      const norm = input.toLowerCase()
      if (["ja", "yes", "y"].includes(norm)) {
        await chatRunFlow()
        return
      }
      if (["nein", "no", "n"].includes(norm)) {
        pushAssistant(
          "Okay. Was möchtest du ändern?\n• `agent` (Agententyp)\n• `prio` (Prioritäten)\n• `level` (Erfahrung)\n• `learn` (Lernpräferenz)\n• `usecase` (Use Case Text)"
        )
        // reuse confirm step but interpret next message
        setChatStep("confirm")
        return
      }

      // interpret edit commands
      if (norm.includes("agent")) {
        pushAssistant("Alles klar — welcher Agententyp? (z.B. Chatbot, Workflow-Agent, Multi-Agent-System)")
        setChatStep("agentType")
        return
      }
      if (norm.includes("prio")) {
        pushAssistant("Okay — wähle Prioritäten (rag/tools/speed/memory/privacy/multi). Schreibe „weiter“ wenn fertig.")
        setChatStep("priorities")
        return
      }
      if (norm.includes("level")) {
        pushAssistant("Okay — beginner/intermediate/expert?")
        setChatStep("experience")
        return
      }
      if (norm.includes("learn")) {
        pushAssistant("Okay — learn oder simple?")
        setChatStep("learning")
        return
      }
      if (norm.includes("usecase")) {
        pushAssistant("Okay — bitte Use Case neu beschreiben.")
        setChatStep("useCase")
        return
      }

      pushAssistant("Bitte antworte mit **ja** oder **nein** (oder nenne, was du ändern willst).")
      return
    }

    if (chatStep === "results") {
      const norm = input.toLowerCase()
      if (norm.startsWith("ja")) {
        // User wants frameworks instead of agents (after UC results)
        pushAssistant("Alles klar — ich zeige dir jetzt Framework-Empfehlungen…")
        try {
          const resAg = await fetch("/api/agent", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...chatPayload, force_frameworks: true }),
          })
          const dataAg = await resAg.json()
          if (!resAg.ok) throw new Error(dataAg?.detail || dataAg?.error || "Fehler beim Laden der Frameworks.")

          let parsed: any = null
          try {
            parsed = JSON.parse(dataAg?.answer ?? "{}")
          } catch {
            parsed = null
          }
          const frameworks: FrameworkRec[] = Array.isArray(parsed?.framework_recommendations)
            ? parsed.framework_recommendations
            : []
          pushAssistant("Hier sind die **Framework-Empfehlungen**:", { kind: "results_frameworks", frameworks })
        } catch (e: any) {
          pushAssistant(`❌ Fehler: ${String(e?.message || e)}`)
        }
        return
      }
      if (norm.startsWith("nein")) {
        pushAssistant("Alles klar. Wenn du willst, kannst du den Chat neu starten oder etwas ändern.")
        return
      }
      pushAssistant("Wenn du Frameworks sehen willst, antworte mit **ja**. Sonst mit **nein**.")
      return
    }
  }

  // ---------------------------
  // Render
  // ---------------------------
  return (
    <div className="min-h-screen bg-white">
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between gap-6 mb-8">
          <div className="flex items-center gap-4">
            <img src="/bosch_logo.png" alt="Bosch Logo" className="h-10" />
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Framework Consultant</h1>
              <p className="text-gray-600">Vorlage oder Chat-Assistent (für Anfänger) – gleicher Prozess, anderes UI.</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant={mode === "template" ? "default" : "outline"}
              className={mode === "template" ? "bg-[#E20015] hover:bg-[#c10012] text-white" : ""}
              onClick={() => {
                setMode("template")
                resetAllTemplate()
              }}
            >
              Vorlage
            </Button>
            <Button
              variant={mode === "chat" ? "default" : "outline"}
              className={mode === "chat" ? "bg-[#E20015] hover:bg-[#c10012] text-white" : ""}
              onClick={() => {
                setMode("chat")
                resetAllTemplate()
                if (!chatMessages.length) startChat()
              }}
            >
              Chat-Assistent
            </Button>
          </div>
        </div>

        {/* Error (template mode only) */}
        {errorMsg && mode === "template" && (
          <Card className="mb-6 border-red-300">
            <CardHeader>
              <CardTitle className="text-red-700">Fehler</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-red-700">{errorMsg}</p>
              <Button className="mt-4" onClick={() => setErrorMsg(null)}>
                OK
              </Button>
            </CardContent>
          </Card>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Sidebar */}
          <div className="lg:col-span-3">
            <Card className="sticky top-6">
              <CardHeader>
                <CardTitle>Navigation</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="text-sm text-gray-600">
                  <p className="mb-2">
                    <b>Vorlage:</b> klassische Fragen als Formular.
                  </p>
                  <p>
                    <b>Chat-Assistent:</b> führt Anfänger Schritt für Schritt.
                  </p>
                </div>

                <div className="space-y-2">
                  <Button
                    variant={mode === "template" ? "default" : "outline"}
                    className={mode === "template" ? "w-full bg-[#E20015] hover:bg-[#c10012] text-white" : "w-full"}
                    onClick={() => {
                      setMode("template")
                      resetAllTemplate()
                    }}
                  >
                    Vorlage öffnen
                  </Button>

                  <Button
                    variant={mode === "chat" ? "default" : "outline"}
                    className={mode === "chat" ? "w-full bg-[#E20015] hover:bg-[#c10012] text-white" : "w-full"}
                    onClick={() => {
                      setMode("chat")
                      if (!chatMessages.length) startChat()
                    }}
                  >
                    Chat starten
                  </Button>

                  {mode === "chat" && (
                    <Button variant="outline" className="w-full" onClick={startChat}>
                      Chat zurücksetzen
                    </Button>
                  )}

                  {mode === "template" && (
                    <Button variant="outline" className="w-full" onClick={resetAllTemplate}>
                      Vorlage zurücksetzen
                    </Button>
                  )}
                </div>

                {mode === "chat" && (
                  <div className="pt-4 text-xs text-gray-500">
                    <div className="mb-1"><b>Aktuelle Antworten</b></div>
                    <div>Agent: {chatAgentType || "—"}</div>
                    <div>Prio: {chatPriorities.length ? chatPriorities.join(", ") : "—"}</div>
                    <div>Level: {chatExperience || "—"}</div>
                    <div>Learn: {chatLearning || "—"}</div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Main */}
          <div className="lg:col-span-9">
            {/* ---------------- Template mode ---------------- */}
            {mode === "template" && (
              <>
                {phase === "form" && (
                  <>
                    {/* STEP 1 */}
                    <Card className="mb-6">
                      <CardHeader>
                        <CardTitle>Was soll dein Agent tun?</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <Select onValueChange={(v) => setAgentType(v)}>
                          <SelectTrigger className="w-full">
                            <SelectValue placeholder="Bitte auswählen..." />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="Chatbot">Chatbot</SelectItem>
                            <SelectItem value="Daten-Agent">Daten-Agent</SelectItem>
                            <SelectItem value="Workflow-Agent">Workflow-Agent</SelectItem>
                            <SelectItem value="Analyse-Agent">Analyse-Agent</SelectItem>
                            <SelectItem value="Multi-Agent-System">Multi-Agent-System</SelectItem>
                            <SelectItem value="unknown">Ich weiß es noch nicht</SelectItem>
                          </SelectContent>
                        </Select>
                      </CardContent>
                    </Card>

                    {/* STEP 2 */}
                    <Card className="mb-6">
                      <CardHeader>
                        <CardTitle>Was ist dir wichtig?</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        {PRIORITY_OPTIONS.map(({ key, label }) => (
                          <div key={key} className="flex items-center space-x-3">
                            <Checkbox checked={priorities.includes(key)} onCheckedChange={() => togglePriority(key)} />
                            <span>{label}</span>
                          </div>
                        ))}
                      </CardContent>
                    </Card>

                    {/* STEP 3 */}
                    <Card className="mb-6">
                      <CardHeader>
                        <CardTitle>Wie gut schätzen Sie sich im Erstellen von Agenten ein?</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <Select onValueChange={setExperienceLevel}>
                          <SelectTrigger className="w-full">
                            <SelectValue placeholder="Erfahrungslevel auswählen" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="beginner">Anfänger</SelectItem>
                            <SelectItem value="intermediate">Fortgeschritten</SelectItem>
                            <SelectItem value="expert">Experte</SelectItem>
                          </SelectContent>
                        </Select>
                      </CardContent>
                    </Card>

                    {/* STEP 4 */}
                    <Card className="mb-6">
                      <CardHeader>
                        <CardTitle>
                          Wollen Sie etwas dazu lernen oder eine einfache Lösung basierend auf Ihren Kenntnissen umsetzen?
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <Select onValueChange={setLearningPreference}>
                          <SelectTrigger className="w-full">
                            <SelectValue placeholder="Option auswählen" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="learn">Etwas dazu lernen</SelectItem>
                            <SelectItem value="simple">Einfache Lösung</SelectItem>
                          </SelectContent>
                        </Select>
                      </CardContent>
                    </Card>

                    {/* STEP 5 */}
                    <Card className="mb-6">
                      <CardHeader>
                        <CardTitle>Erläutere deinen Use-Case</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <Textarea
                          value={useCase}
                          onChange={(e) => setUseCase(e.target.value)}
                          placeholder="Beschreibe deinen Use Case..."
                          className="h-32"
                        />
                      </CardContent>
                    </Card>

                    <Button
                      className="w-full text-lg py-6 bg-[#E20015] hover:bg-[#c10012] text-white"
                      onClick={fetchBoschUseCases}
                      disabled={loading || !canSubmit}
                    >
                      {loading ? "Lädt..." : "Vorschläge erhalten →"}
                    </Button>

                    {!canSubmit && (
                      <p className="text-sm text-gray-500 mt-3 text-center">
                        Bitte wähle Agententyp, Erfahrungslevel, Lernpräferenz und beschreibe deinen Use Case.
                      </p>
                    )}
                  </>
                )}

                {/* Bosch use cases screen */}
                {phase === "bosch" && (
                  <>
                    <div className="flex items-center justify-between mb-6">
                      <h2 className="text-2xl font-semibold">Passende Bosch-Agenten / Use Cases</h2>
                      <Button variant="outline" onClick={resetAllTemplate}>Zurück</Button>
                    </div>

                    <p className="text-gray-600 mb-6">
                      Du kannst einen Use Case auswählen oder stattdessen Frameworks anzeigen lassen.
                    </p>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                      {boschUseCases.map((uc, i) => (
                        <Card key={i} className="p-6 rounded-3xl border shadow-md bg-white flex flex-col justify-between">
                          <CardHeader className="text-center">
                            <CardTitle className="text-xl font-bold">{uc.title}</CardTitle>
                          </CardHeader>
                          <CardContent className="text-center flex flex-col gap-3">
                            <p className="text-gray-600 text-sm leading-relaxed line-clamp-6">{uc.summary}</p>
                            <div className="text-blue-700 font-bold text-lg mt-2">
                              {uc.match_percent ?? pct(uc.score)}%
                            </div>
                            <Button
                              className="mx-auto mt-2 w-full bg-[#E20015] hover:bg-[#c10012] text-white"
                              onClick={() => {
                                setSelectedBosch(uc)
                                setPhase("selectedUseCase")
                              }}
                            >
                              Agent benutzen
                            </Button>
                          </CardContent>
                        </Card>
                      ))}
                    </div>

                    <div className="flex justify-center mt-8">
                      <Button
                        className="bg-gray-900 text-white"
                        onClick={async () => {
                          setPhase("frameworks")
                          await fetchFrameworks(true)
                        }}
                        disabled={loading}
                      >
                        {loading ? "Lädt..." : "Passt nicht – Frameworks anzeigen"}
                      </Button>
                    </div>
                  </>
                )}

                {/* Selected use case */}
                {phase === "selectedUseCase" && selectedBosch && (
                  <>
                    <div className="flex items-center justify-between mb-6">
                      <h2 className="text-2xl font-semibold">Ausgewählter Bosch-Agent / Use Case</h2>
                      <Button variant="outline" onClick={() => setPhase("bosch")}>Zurück</Button>
                    </div>

                    <Card className="p-6 rounded-3xl border shadow-md bg-white">
                      <CardHeader>
                        <CardTitle className="text-xl font-bold">{selectedBosch.title}</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        <p className="text-gray-700 whitespace-pre-wrap">{selectedBosch.summary}</p>
                        <div className="text-blue-700 font-bold text-lg">
                          Match: {selectedBosch.match_percent ?? pct(selectedBosch.score)}%
                        </div>

                        <div className="flex flex-col md:flex-row gap-3">
                          <Button
                            className="bg-[#E20015] hover:bg-[#c10012] text-white"
                            onClick={() => alert("Hier könntest du den Bosch-Agenten ausführen oder Details anzeigen.")}
                          >
                            Weiter
                          </Button>
                          <Button
                            variant="outline"
                            onClick={async () => {
                              setPhase("frameworks")
                              await fetchFrameworks(true)
                            }}
                          >
                            Stattdessen Frameworks anzeigen
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  </>
                )}

                {/* Frameworks */}
                {phase === "frameworks" && (
                  <>
                    <div className="flex items-center justify-between mb-6">
                      <h2 className="text-2xl font-semibold">Framework-Empfehlungen</h2>
                      <Button variant="outline" onClick={resetAllTemplate}>Zurück</Button>
                    </div>

                    {loading && <p className="text-gray-600">Lädt Framework-Empfehlungen...</p>}

                    {!loading && frameworkResults.length === 0 && (
                      <Card className="p-6">
                        <CardHeader>
                          <CardTitle>Keine Empfehlungen verfügbar</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <p className="text-gray-600 text-sm">
                            Es wurden keine Framework-Empfehlungen geliefert. Prüfe Backend-Konsole und /agent Response.
                          </p>
                        </CardContent>
                      </Card>
                    )}

                    {frameworkResults.length > 0 && (
                      <>
                        <p className="text-gray-600 mb-6">
                          Diese Frameworks passen basierend auf deinen Anforderungen am besten.
                        </p>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                          {frameworkResults.map((rec, i) => (
                            <Card key={i} className="p-6 rounded-3xl border shadow-md bg-white flex flex-col justify-between">
                              <CardHeader className="text-center">
                                <CardTitle className="text-xl font-bold">{rec.framework}</CardTitle>
                              </CardHeader>
                              <CardContent className="text-center flex flex-col gap-3">
                                <p className="text-gray-600 text-sm leading-relaxed line-clamp-6">
                                  {rec.description || "Keine Beschreibung vorhanden."}
                                </p>
                                <div className="text-blue-700 font-bold text-lg mt-2">
                                  {rec.match_percent ?? pct(rec.score)}%
                                </div>
                                <Button
                                  className="mx-auto mt-2 w-full bg-[#E20015] hover:bg-[#c10012] text-white"
                                  onClick={() => alert(`Nächster Schritt: Setup-Anleitung für ${rec.framework}`)}
                                >
                                  Verwenden
                                </Button>
                              </CardContent>
                            </Card>
                          ))}
                        </div>
                      </>
                    )}
                  </>
                )}
              </>
            )}

            {/* ---------------- Chat mode ---------------- */}
            {mode === "chat" && (
              <Card className="min-h-[70vh] flex flex-col">
                <CardHeader className="border-b">
                  <CardTitle>Chat-Assistent (für Anfänger)</CardTitle>
                </CardHeader>

                {/* Messages */}
                <CardContent className="flex-1 overflow-y-auto py-4 space-y-3">
                  {chatMessages.length === 0 && (
                    <div className="text-gray-600 text-sm">
                      Klicke links auf „Chat starten“.
                    </div>
                  )}

                  {chatMessages.map((m) => (
                    <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                      <div
                        className={
                          m.role === "user"
                            ? "max-w-[80%] rounded-2xl px-4 py-3 bg-gray-900 text-white"
                            : "max-w-[80%] rounded-2xl px-4 py-3 bg-gray-100 text-gray-900"
                        }
                      >
                        <div className="whitespace-pre-wrap text-sm leading-relaxed">{m.content}</div>

                        {/* Embedded results cards */}
                        {m.meta?.kind === "results_agents" && m.meta.agents && (
                          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
                            {m.meta.agents.slice(0, 3).map((a, idx) => (
                              <div key={idx} className="rounded-2xl border bg-white p-4 shadow-sm">
                                <div className="font-semibold">{a.title}</div>
                                <div className="text-xs text-gray-600 mt-2 line-clamp-5 whitespace-pre-wrap">
                                  {a.summary}
                                </div>
                                <div className="mt-3 text-blue-700 font-bold">
                                  {a.match_percent ?? pct(a.score)}%
                                </div>
                                <Button
                                  className="mt-3 w-full bg-[#E20015] hover:bg-[#c10012] text-white"
                                  onClick={() => alert("Hier könntest du den Agenten-Detailflow öffnen.")}
                                >
                                  Agent auswählen
                                </Button>
                              </div>
                            ))}
                          </div>
                        )}

                        {m.meta?.kind === "results_frameworks" && m.meta.frameworks && (
                          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
                            {m.meta.frameworks.slice(0, 3).map((f, idx) => (
                              <div key={idx} className="rounded-2xl border bg-white p-4 shadow-sm">
                                <div className="font-semibold">{f.framework}</div>
                                <div className="text-xs text-gray-600 mt-2 line-clamp-5">
                                  {f.description || "Keine Beschreibung vorhanden."}
                                </div>
                                <div className="mt-3 text-blue-700 font-bold">
                                  {f.match_percent ?? pct(f.score)}%
                                </div>
                                <Button
                                  className="mt-3 w-full bg-[#E20015] hover:bg-[#c10012] text-white"
                                  onClick={() => alert(`Setup-Anleitung für ${f.framework}`)}
                                >
                                  Verwenden
                                </Button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}

                  {/* inline quick controls for priority picking */}
                  {chatStep === "priorities" && (
                    <div className="mt-2 rounded-2xl border bg-white p-4">
                      <div className="text-sm font-semibold mb-3">Prioritäten auswählen (optional)</div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        {PRIORITY_OPTIONS.map((opt) => (
                          <label key={opt.key} className="flex items-center gap-3 text-sm">
                            <Checkbox
                              checked={chatPriorities.includes(opt.key)}
                              onCheckedChange={() => toggleChatPriority(opt.key)}
                            />
                            <span>{opt.label}</span>
                          </label>
                        ))}
                      </div>
                      <div className="mt-3 text-xs text-gray-600">
                        Wenn du fertig bist: schreibe <b>weiter</b>.
                      </div>
                    </div>
                  )}

                  {/* inline quick controls for agent type */}
                  {chatStep === "agentType" && (
                    <div className="mt-2 rounded-2xl border bg-white p-4">
                      <div className="text-sm font-semibold mb-3">Schnellauswahl Agententyp</div>
                      <div className="flex flex-wrap gap-2">
                        {AGENT_TYPES.filter((x) => x !== "unknown").map((t) => (
                          <Button
                            key={t}
                            variant="outline"
                            onClick={() => {
                              pushUser(t)
                              setChatAgentType(t)
                              pushAssistant(`Okay: **${t}**.\n\nAls nächstes: Prioritäten auswählen oder „weiter“.`)
                              setChatStep("priorities")
                            }}
                          >
                            {t}
                          </Button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* inline quick controls for experience */}
                  {chatStep === "experience" && (
                    <div className="mt-2 rounded-2xl border bg-white p-4">
                      <div className="text-sm font-semibold mb-3">Schnellauswahl Erfahrungslevel</div>
                      <div className="flex flex-wrap gap-2">
                        {EXPERIENCE_LEVELS.map((x) => (
                          <Button
                            key={x.value}
                            variant="outline"
                            onClick={() => {
                              pushUser(x.value)
                              setChatExperience(x.value)
                              pushAssistant("Super.\n\nlearn oder simple?")
                              setChatStep("learning")
                            }}
                          >
                            {x.label}
                          </Button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* inline quick controls for learning */}
                  {chatStep === "learning" && (
                    <div className="mt-2 rounded-2xl border bg-white p-4">
                      <div className="text-sm font-semibold mb-3">Schnellauswahl Lernpräferenz</div>
                      <div className="flex flex-wrap gap-2">
                        {LEARNING_PREFS.map((x) => (
                          <Button
                            key={x.value}
                            variant="outline"
                            onClick={() => {
                              pushUser(x.value)
                              setChatLearning(x.value)
                              pushAssistant("Jetzt beschreibe bitte deinen Use Case in 1–3 Sätzen.")
                              setChatStep("useCase")
                            }}
                          >
                            {x.label}
                          </Button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Confirm shortcuts */}
                  {chatStep === "confirm" && (
                    <div className="mt-2 rounded-2xl border bg-white p-4">
                      <div className="text-sm font-semibold mb-3">Bestätigen</div>
                      <div className="flex gap-2">
                        <Button
                          className="bg-[#E20015] hover:bg-[#c10012] text-white"
                          onClick={chatRunFlow}
                        >
                          Ja, starten
                        </Button>
                        <Button
                          variant="outline"
                          onClick={() => {
                            pushAssistant(
                              "Was möchtest du ändern?\n• `agent`\n• `prio`\n• `level`\n• `learn`\n• `usecase`"
                            )
                          }}
                        >
                          Nein, ändern
                        </Button>
                      </div>
                    </div>
                  )}

                  <div ref={chatEndRef} />
                </CardContent>

                {/* Input */}
                <div className="border-t p-4 flex gap-2">
                  <Textarea
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    placeholder="Schreibe deine Antwort…"
                    className="h-12 min-h-12 resize-none"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault()
                        onChatSubmit()
                      }
                    }}
                  />
                  <Button
                    className="bg-[#E20015] hover:bg-[#c10012] text-white"
                    onClick={onChatSubmit}
                    disabled={chatStep === "running"}
                  >
                    Senden
                  </Button>
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
