"use client"

import { useMemo, useState } from "react"
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
  score: number
  description?: string
  match_reason?: string
  pros?: string[]
  cons?: string[]
  recommendation?: string
  match_percent?: number
  url?: string
}

type BoschUseCase = {
  title: string
  summary: string
  score: number
  metadata?: Record<string, any>
}

type Phase = "form" | "bosch" | "frameworks" | "selectedUseCase"

export default function Home() {
  const [agentType, setAgentType] = useState("")
  const [useCase, setUseCase] = useState("")
  const [experienceLevel, setExperienceLevel] = useState("")
  const [learningPreference, setLearningPreference] = useState("")
  const [priorities, setPriorities] = useState<string[]>([])

  const [phase, setPhase] = useState<Phase>("form")
  const [loading, setLoading] = useState(false)

  const [boschUseCases, setBoschUseCases] = useState<BoschUseCase[]>([])
  const [selectedBosch, setSelectedBosch] = useState<BoschUseCase | null>(null)

  const [frameworkResults, setFrameworkResults] = useState<FrameworkRec[]>([])
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const formPayload = useMemo(() => {
    return {
      agent_type: agentType,
      priorities,
      use_case: useCase,
      experience_level: experienceLevel,
      learning_preference: learningPreference,
    }
  }, [agentType, priorities, useCase, experienceLevel, learningPreference])

  const togglePriority = (key: string) => {
    setPriorities((prev) =>
      prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key]
    )
  }

  const canSubmit = Boolean(agentType && useCase && experienceLevel && learningPreference)

  const resetAll = () => {
    setPhase("form")
    setLoading(false)
    setErrorMsg(null)
    setBoschUseCases([])
    setSelectedBosch(null)
    setFrameworkResults([])
  }

  const fetchFrameworks = async (force: boolean) => {
    setLoading(true)
    setErrorMsg(null)
    setFrameworkResults([])

    try {
      const payload = { ...formPayload, force_frameworks: force }

      const res = await fetch("/api/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        cache: "no-store",
      })

      const data = await res.json()

      if (!res.ok) {
        throw new Error(
          data?.detail || data?.error || "Fehler beim Laden der Frameworks."
        )
      }

      // --- Debug (entscheidend) ---
      console.log("RAW /api/agent response:", data)

      // Fall A: Proxy gibt Backend direkt zurück
      const direct = Array.isArray(data?.framework_recommendations)
        ? data.framework_recommendations
        : null

      // Fall B: Proxy wrappt in { answer: "JSON_STRING" }
      let wrapped: any = null
      if (!direct && typeof data?.answer === "string") {
        try {
          wrapped = JSON.parse(data.answer)
        } catch {
          wrapped = null
        }
      }

      const recs: FrameworkRec[] = direct
        ? direct
        : Array.isArray(wrapped?.framework_recommendations)
          ? wrapped.framework_recommendations
          : []

      console.log("FINAL recs length:", recs.length)

      setFrameworkResults(recs)
    } catch (e: any) {
      setErrorMsg(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }

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
        cache: "no-store",
      })

      const data = await res.json()

      if (!res.ok) {
        throw new Error(data?.detail || data?.error || "Fehler beim Laden der Bosch Use Cases.")
      }

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

  return (
    <div className="max-w-6xl mx-auto p-10">
      <div className="flex flex-col items-center mb-12 mt-4">
        <img src="/bosch_logo.png" alt="Bosch Logo" className="h-12 mb-3" />
        <h1 className="text-4xl font-bold tracking-tight">Framework Consultant</h1>
        <p className="text-gray-600 mt-2">Finden Sie das passende Agenten-Setup für Ihren Anwendungsfall.</p>
      </div>

      {errorMsg && (
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

      {phase === "form" && (
        <>
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

          <Card className="mb-6">
            <CardHeader>
              <CardTitle>Was ist dir wichtig?</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {[
                { key: "speed", label: "Schnell & leichtgewichtig ⚡" },
                { key: "tools", label: "Viele Integrationen / Tools 🔌" },
                { key: "memory", label: "Gute Gedächtnisfunktionen 🧠" },
                { key: "rag", label: "Dokumenten-Suche (RAG) 📄" },
                { key: "privacy", label: "Datenschutzfreundlich 🔒" },
                { key: "multi", label: "Multi-Agent-Fähig 🤖" },
              ].map(({ key, label }) => (
                <div key={key} className="flex items-center space-x-3">
                  <Checkbox checked={priorities.includes(key)} onCheckedChange={() => togglePriority(key)} />
                  <span>{label}</span>
                </div>
              ))}
            </CardContent>
          </Card>

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

          <Card className="mb-6">
            <CardHeader>
              <CardTitle>Wollen Sie etwas dazu lernen oder eine einfache Lösung umsetzen?</CardTitle>
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

      {phase === "bosch" && (
        <>
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-semibold">Passende Bosch-Agenten / Use Cases</h2>
            <Button variant="outline" onClick={resetAll}>Zurück</Button>
          </div>

          <p className="text-gray-600 mb-6">
            Du kannst einen Use Case auswählen oder stattdessen Frameworks anzeigen lassen.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {boschUseCases.map((uc, i) => (
              <Card key={i} className="p-6 rounded-3xl border shadow-md bg-white flex flex-col justify-between">
                <CardHeader className="text-center">
                  <CardTitle className="text-xl font-bold">{uc.title}</CardTitle>
                </CardHeader>
                <CardContent className="text-center flex flex-col gap-3">
                  <p className="text-gray-600 text-sm leading-relaxed">{uc.summary}</p>
                  <div className="text-blue-700 font-bold text-lg mt-2">
                    {Math.round((uc.score ?? 0) * 100)}%
                  </div>
                  <Button
                    className="mx-auto mt-2 w-full bg-[#E20015] hover:bg-[#c10012] text-white"
                    onClick={() => { setSelectedBosch(uc); setPhase("selectedUseCase") }}
                  >
                    Agent benutzen
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="flex justify-center mt-10">
            <Button
              className="bg-gray-900 text-white"
              onClick={async () => { setPhase("frameworks"); await fetchFrameworks(true) }}
              disabled={loading}
            >
              {loading ? "Lädt..." : "Passt nicht – Frameworks anzeigen"}
            </Button>
          </div>
        </>
      )}

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
              <p className="text-gray-700">{selectedBosch.summary}</p>
              <div className="text-blue-700 font-bold text-lg">
                Match: {Math.round((selectedBosch.score ?? 0) * 100)}%
              </div>

              <div className="flex flex-col md:flex-row gap-3">
                <Button
                  className="bg-[#E20015] hover:bg-[#c10012] text-white"
                  onClick={() => alert("Nächster Schritt: Bosch-Agent ausführen / Details anzeigen")}
                >
                  Weiter
                </Button>

                <Button
                  variant="outline"
                  onClick={async () => { setPhase("frameworks"); await fetchFrameworks(true) }}
                >
                  Stattdessen Frameworks anzeigen
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {phase === "frameworks" && (
        <>
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-semibold">Framework-Empfehlungen</h2>
            <Button variant="outline" onClick={resetAll}>Zurück</Button>
          </div>

          {loading && <p className="text-gray-600">Lädt Framework-Empfehlungen...</p>}

          {!loading && frameworkResults.length === 0 && (
            <Card className="p-6">
              <CardHeader>
                <CardTitle>Keine Empfehlungen verfügbar</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-gray-600 text-sm">
                  Öffne DevTools → Console. Dort steht: "RAW /api/agent response" und "FINAL recs length".
                </p>
              </CardContent>
            </Card>
          )}

          {frameworkResults.length > 0 && (
            <>
              <p className="text-gray-600 mb-6">
                Diese Frameworks passen basierend auf deinen Anforderungen am besten.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                {frameworkResults.map((rec, i) => (
                  <Card key={i} className="p-6 rounded-3xl border shadow-md bg-white flex flex-col justify-between">
                    <CardHeader className="text-center">
                      <CardTitle className="text-xl font-bold">{rec.framework}</CardTitle>
                    </CardHeader>

                    <CardContent className="text-center flex flex-col gap-3">
                      <p className="text-gray-600 text-sm leading-relaxed">
                        {rec.description || "Keine Beschreibung vorhanden."}
                      </p>

                      <div className="text-blue-700 font-bold text-lg mt-2">
                        {Math.round((rec.score ?? 0) * 100)}%
                      </div>

                      <Button
                        className="mx-auto mt-2 w-full bg-[#E20015] hover:bg-[#c10012] text-white"
                        onClick={() => alert(`Nächster Schritt: Setup-Anleitung für ${rec.framework}`)}
                      >
                        use
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
