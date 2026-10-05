import React, { useState, useEffect } from 'react'
import {
  CheckCircle2,
  AlertTriangle,
  Upload,
  Play,
  Send,
  ShieldCheck,
  LogOut,
  RefreshCw,
  Plus,
  ArrowRight,
  FileSpreadsheet,
  Eye,
  Copy,
  Check,
  Layers,
  Sparkles,
  Info,
  ExternalLink,
  XCircle,
  Cpu
} from 'lucide-react'

// --- Interfaces ---

interface UserProfile {
  id: string
  email: string
  full_name: string
  role: string
  tenant_id: string
  tenant_name: string
  mfa_enabled: boolean
}

interface Client {
  id: string
  legal_name: string
  trading_name?: string
  tin_raw: string
  tin_normalised: string
  vat_number?: string
  vat_category: string
  default_currency: string
  contact_name?: string
  contact_email?: string
  contact_phone?: string
  city?: string
}

interface EngagementSummary {
  id: string
  reference: string
  client_id: string
  client_name: string
  client_tin: string
  period_start: string
  period_end: string
  currency: string
  status: string
  ap_lines_count: number
  zimra_lines_count: number
  matches_count: number
  exceptions_count: number
  vat_at_risk_by_currency: Record<string, number>
}

interface MatchItem {
  id: string
  pass_id: string
  confidence: number
  supplier_name: string
  invoice_number: string
  invoice_date: string
  currency: string
  ap_gross: number
  zimra_gross: number
  ap_vat: number
  zimra_vat: number
}

interface ExceptionItem {
  id: string
  primary_class: string
  rule_id: string
  vat_at_risk: number
  currency: string
  is_recoverable: boolean
  is_advisory: boolean
  status: string
  supplier_name: string
  invoice_number: string
  invoice_date: string
  evidence: Record<string, any>
}

interface SupplierItem {
  supplier_name: string
  supplier_tin: string
  total_vat_at_risk: number
  currency: string
  exception_count: number
  invoices: Array<{
    invoice_number: string
    date: string
    gross: number
    vat: number
    exception_class: string
  }>
}

interface LetterResponse {
  letter_ref: string
  generated_at: string
  supplier_name: string
  supplier_tin: string
  recipient_email: string
  vat_at_risk: number
  currency: string
  invoices_affected: any[]
  letter_text: string
}

interface RealtimeCheck {
  rule: string
  name: string
  status: 'PASS' | 'WARN' | 'FAIL' | 'INFO'
  details: string
}

interface LocalZimraRegistry {
  found: boolean
  status: string
  details: string
  zimra_gross?: number | null
  zimra_vat?: number | null
}

interface RecognizedDocument {
  buyer_name: string
  buyer_tin: string
  buyer_vat_number?: string
  supplier_name: string
  supplier_tin: string
  invoice_number: string
  invoice_date: string
  currency: string
  city: string
  net_amount: number
  vat_amount: number
  gross_amount: number
  confidence_score: number
  resolution: {
    status: 'matched_existing' | 'new_discovered'
    match_reason: string
    client_id?: string
    legal_name: string
    tin_normalised: string
    vat_category: string
    default_currency: string
    city?: string
    confidence: number
  }
  fiscal_details?: {
    device_serial?: string | null
    fiscal_day?: string | null
    verification_code?: string | null
  }
  realtime_validation?: {
    is_statutory_valid: boolean
    statutory_rate_percent: number
    zimra_portal_url: string
    fiscal_details: {
      device_serial?: string | null
      fiscal_day?: string | null
      verification_code?: string | null
    }
    local_zimra_registry: LocalZimraRegistry
    checks: RealtimeCheck[]
  }
  zimra_portal_url?: string
}

export default function App() {
  // Navigation & View State
  const [activeTab, setActiveTab] = useState<'dashboard' | 'clients' | 'reconciliation' | 'letters'>('dashboard')
  const [reconcileStep, setReconcileStep] = useState<number>(1)

  // Auth State
  const [token, setToken] = useState<string | null>(localStorage.getItem('fira_token'))
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null)
  const [loginEmail, setLoginEmail] = useState('admin@fira.local')
  const [loginPassword, setLoginPassword] = useState('FiraSecure2026!')
  const [loginMfa, setLoginMfa] = useState('')
  const [authError, setAuthError] = useState<string | null>(null)
  const [showLoginModal, setShowLoginModal] = useState(false)

  // Data State
  const [clients, setClients] = useState<Client[]>([])
  const [engagements, setEngagements] = useState<EngagementSummary[]>([])
  const [selectedEngId, setSelectedEngId] = useState<string>('')
  const [matches, setMatches] = useState<MatchItem[]>([])
  const [exceptions, setExceptions] = useState<ExceptionItem[]>([])
  const [suppliers, setSuppliers] = useState<SupplierItem[]>([])
  const [selectedSupplierForLetter, setSelectedSupplierForLetter] = useState<SupplierItem | null>(null)
  const [generatedLetter, setGeneratedLetter] = useState<LetterResponse | null>(null)
  const [copiedLetter, setCopiedLetter] = useState(false)
  const [activeEvidenceModal, setActiveEvidenceModal] = useState<ExceptionItem | null>(null)

  // Document Auto-Recognition State
  const [isRecognizing, setIsRecognizing] = useState(false)
  const [recognizedDoc, setRecognizedDoc] = useState<RecognizedDocument | null>(null)
  const [recognizeError, setRecognizeError] = useState<string | null>(null)
  const [isUploadingAp, setIsUploadingAp] = useState(false)
  const [isUploadingZimra, setIsUploadingZimra] = useState(false)

  // Modals & Forms
  const [showNewClientModal, setShowNewClientModal] = useState(false)
  const [newClientForm, setNewClientForm] = useState({
    legal_name: '',
    trading_name: '',
    tin_raw: '',
    vat_category: 'C',
    default_currency: 'USD',
    city: 'Harare',
    contact_email: '',
  })
  const [clientFormError, setClientFormError] = useState<string | null>(null)

  const [showNewEngModal, setShowNewEngModal] = useState(false)
  const [newEngForm, setNewEngForm] = useState({
    client_id: '',
    reference: `ENG-${new Date().getFullYear()}-${Math.floor(100 + Math.random() * 900)}`,
    period_start: '2026-01-01',
    period_end: '2026-01-31',
    currency: 'USD',
  })

  // System Status
  const [healthNotice, setHealthNotice] = useState<string>('Loading regulatory parameters...')
  const [apiOnline, setApiOnline] = useState(false)
  const [loading, setLoading] = useState(false)
  const [statusMessage, setStatusMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null)

  // Exception Filter
  const [filterClass, setFilterClass] = useState<string>('ALL')

  // Helper Headers
  const getAuthHeaders = () => ({
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  })

  // 1. Initial Health & Session Check
  useEffect(() => {
    fetch('/api/healthz')
      .then((res) => res.json())
      .then((data) => {
        setApiOnline(data.status === 'ok')
        if (data.notice) setHealthNotice(data.notice)
      })
      .catch(() => setApiOnline(false))
  }, [])

  // 2. Fetch User Profile if Token Exists
  useEffect(() => {
    if (token) {
      fetch('/api/v1/auth/me', { headers: getAuthHeaders() })
        .then((res) => {
          if (!res.ok) throw new Error('Session expired')
          return res.json()
        })
        .then((profile) => {
          setCurrentUser(profile)
          setShowLoginModal(false)
        })
        .catch(() => {
          handleLogout()
        })
    } else {
      setShowLoginModal(true)
    }
  }, [token])

  // 3. Load Clients & Engagements
  const loadData = async () => {
    if (!token) return
    setLoading(true)
    try {
      const [clientsRes, engRes] = await Promise.all([
        fetch('/api/v1/clients', { headers: getAuthHeaders() }),
        fetch('/api/v1/engagements', { headers: getAuthHeaders() }),
      ])
      if (clientsRes.ok) {
        const clientData = await clientsRes.json()
        setClients(clientData)
        if (clientData.length > 0 && !newEngForm.client_id) {
          setNewEngForm((prev) => ({ ...prev, client_id: clientData[0].id }))
        }
      }
      if (engRes.ok) {
        const engData = await engRes.json()
        setEngagements(engData)
        if (engData.length > 0 && !selectedEngId) {
          setSelectedEngId(engData[0].id)
        }
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (currentUser) {
      loadData()
    }
  }, [currentUser])

  // 4. Load Matches & Exceptions for Selected Engagement
  const loadEngagementDetails = async (engId: string) => {
    if (!engId || !token) return
    try {
      const [matchesRes, excRes, suppRes] = await Promise.all([
        fetch(`/api/v1/engagements/${engId}/matches`, { headers: getAuthHeaders() }),
        fetch(`/api/v1/engagements/${engId}/exceptions`, { headers: getAuthHeaders() }),
        fetch(`/api/v1/engagements/${engId}/suppliers`, { headers: getAuthHeaders() }),
      ])
      if (matchesRes.ok) setMatches(await matchesRes.json())
      if (excRes.ok) setExceptions(await excRes.json())
      if (suppRes.ok) setSuppliers(await suppRes.json())
    } catch (err) {
      console.error(err)
    }
  }

  useEffect(() => {
    if (selectedEngId) {
      loadEngagementDetails(selectedEngId)
    }
  }, [selectedEngId])

  // --- Handlers ---

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setAuthError(null)
    setLoading(true)
    try {
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: loginEmail,
          password: loginPassword,
          ...(loginMfa ? { mfa_code: loginMfa } : {}),
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Authentication failed')
      }
      localStorage.setItem('fira_token', data.access_token)
      setToken(data.access_token)
      setShowLoginModal(false)
      setStatusMessage({ text: 'Authenticated successfully', type: 'success' })
    } catch (err: any) {
      setAuthError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = async () => {
    if (token) {
      try {
        await fetch('/api/v1/auth/logout', {
          method: 'POST',
          headers: getAuthHeaders(),
        })
      } catch (err) {
        // ignore
      }
    }
    localStorage.removeItem('fira_token')
    setToken(null)
    setCurrentUser(null)
    setShowLoginModal(true)
  }

  const handleQuickDemoLogin = (email: string) => {
    setLoginEmail(email)
    setLoginPassword('FiraSecure2026!')
  }

  const handleCreateClient = async (e: React.FormEvent) => {
    e.preventDefault()
    setClientFormError(null)
    try {
      const res = await fetch('/api/v1/clients', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(newClientForm),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to create client')
      setShowNewClientModal(false)
      setNewClientForm({
        legal_name: '',
        trading_name: '',
        tin_raw: '',
        vat_category: 'C',
        default_currency: 'USD',
        city: 'Harare',
        contact_email: '',
      })
      loadData()
      setStatusMessage({ text: `Client ${data.legal_name} registered successfully!`, type: 'success' })
    } catch (err: any) {
      setClientFormError(err.message)
    }
  }

  const handleCreateEngagement = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await fetch('/api/v1/engagements', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(newEngForm),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to create engagement')
      setShowNewEngModal(false)
      loadData()
      setSelectedEngId(data.id)
      setActiveTab('reconciliation')
      setStatusMessage({ text: `Engagement ${data.reference} created!`, type: 'success' })
    } catch (err: any) {
      alert(err.message)
    }
  }

  const handleSeedSampleData = async () => {
    if (!selectedEngId) return
    setLoading(true)
    try {
      const res = await fetch(`/api/v1/engagements/${selectedEngId}/seed-sample-data`, {
        method: 'POST',
        headers: getAuthHeaders(),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Seeding failed')
      setStatusMessage({ text: data.message, type: 'success' })
      await loadData()
      await loadEngagementDetails(selectedEngId)
      setReconcileStep(2)
    } catch (err: any) {
      setStatusMessage({ text: err.message, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const handleRunReconciliation = async () => {
    if (!selectedEngId) return
    setLoading(true)
    try {
      const res = await fetch(`/api/v1/engagements/${selectedEngId}/reconcile`, {
        method: 'POST',
        headers: getAuthHeaders(),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Reconciliation failed')
      setStatusMessage({
        text: `Reconciliation executed in ${data.stats.duration_ms}ms: ${data.stats.matched_count} matches, ${data.stats.exceptions_count} exceptions.`,
        type: 'success',
      })
      await loadData()
      await loadEngagementDetails(selectedEngId)
      setReconcileStep(3)
    } catch (err: any) {
      setStatusMessage({ text: err.message, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const handleGenerateLetter = async (supplier: SupplierItem) => {
    if (!selectedEngId) return
    setLoading(true)
    try {
      const res = await fetch(`/api/v1/engagements/${selectedEngId}/supplier-letters`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          supplier_name: supplier.supplier_name,
          supplier_tin: supplier.supplier_tin,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Letter generation failed')
      setGeneratedLetter(data)
      setSelectedSupplierForLetter(supplier)
    } catch (err: any) {
      alert(err.message)
    } finally {
      setLoading(false)
    }
  }

  // --- Document Auto-Recognition & Zero-Friction Onboarding Handlers ---

  const handleRecognizePreset = async (presetName: string) => {
    setIsRecognizing(true)
    setRecognizeError(null)
    setRecognizedDoc(null)
    try {
      const res = await fetch('/api/v1/documents/recognize', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ preset_name: presetName }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Document entity recognition failed')
      setRecognizedDoc(data)
      setStatusMessage({
        text: `Recognized Taxpayer: ${data.buyer_name} (TIN: ${data.buyer_tin}) with ${data.confidence_score}% confidence!`,
        type: 'success',
      })
    } catch (err: any) {
      setRecognizeError(err.message)
    } finally {
      setIsRecognizing(false)
    }
  }

  const handleRecognizeFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setIsRecognizing(true)
    setRecognizeError(null)
    setRecognizedDoc(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch('/api/v1/documents/recognize-file', {
        method: 'POST',
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: formData,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Document entity recognition failed')
      setRecognizedDoc(data)
      setStatusMessage({
        text: `Scanned ${file.name}: Auto-recognized ${data.buyer_name} (TIN: ${data.buyer_tin})!`,
        type: 'success',
      })
    } catch (err: any) {
      setRecognizeError(err.message)
    } finally {
      setIsRecognizing(false)
    }
  }

  const handleAutoOnboardAndStart = async (doc: RecognizedDocument) => {
    setLoading(true)
    try {
      const res = await fetch('/api/v1/documents/auto-onboard', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          buyer_name: doc.buyer_name,
          buyer_tin: doc.buyer_tin,
          currency: doc.currency,
          city: doc.city,
          supplier_name: doc.supplier_name,
          invoice_number: doc.invoice_number,
          gross_amount: doc.gross_amount,
          vat_amount: doc.vat_amount,
        }),
      })
      const eng = await res.json()
      if (!res.ok) throw new Error(eng.detail || 'Auto-onboarding failed')
      await loadData()
      setSelectedEngId(eng.id)
      setActiveTab('reconciliation')
      // Auto seed sample data for realistic reconciliation immediately
      await fetch(`/api/v1/engagements/${eng.id}/seed-sample-data`, {
        method: 'POST',
        headers: getAuthHeaders(),
      })
      await loadEngagementDetails(eng.id)
      setReconcileStep(2)
      setStatusMessage({
        text: `Zero-Touch Setup Complete: ${doc.buyer_name} recognized, registered, and engagement initialized!`,
        type: 'success',
      })
      setRecognizedDoc(null)
    } catch (err: any) {
      alert(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleUploadApFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !selectedEngId) return
    setIsUploadingAp(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch(`/api/v1/engagements/${selectedEngId}/upload-ap`, {
        method: 'POST',
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: formData,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to upload AP ledger')
      await loadEngagementDetails(selectedEngId)
      await loadData()
      setStatusMessage({
        text: `Successfully ingested ${data.lines_ingested} AP ledger rows from ${file.name}!`,
        type: 'success',
      })
    } catch (err: any) {
      alert(err.message)
    } finally {
      setIsUploadingAp(false)
      e.target.value = ''
    }
  }

  const handleUploadZimraFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !selectedEngId) return
    setIsUploadingZimra(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch(`/api/v1/engagements/${selectedEngId}/upload-zimra`, {
        method: 'POST',
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: formData,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to upload ZIMRA claim export')
      await loadEngagementDetails(selectedEngId)
      await loadData()
      setStatusMessage({
        text: `Successfully ingested ${data.lines_ingested} ZIMRA claim rows from ${file.name}!`,
        type: 'success',
      })
    } catch (err: any) {
      alert(err.message)
    } finally {
      setIsUploadingZimra(false)
      e.target.value = ''
    }
  }

  const handleIngestRecognizedInvoice = async (doc: RecognizedDocument) => {
    if (!selectedEngId) {
      alert('Please select or create an engagement first.')
      return
    }
    setLoading(true)
    try {
      const res = await fetch(`/api/v1/engagements/${selectedEngId}/ingest-recognized-document`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          supplier_name: doc.supplier_name,
          supplier_tin: doc.supplier_tin,
          invoice_number: doc.invoice_number,
          invoice_date: doc.invoice_date,
          currency: doc.currency,
          net_amount: doc.net_amount,
          vat_amount: doc.vat_amount,
          gross_amount: doc.gross_amount,
          expense_category: 'Scanned Tax Invoice',
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to ingest invoice into ledger')
      await loadEngagementDetails(selectedEngId)
      await loadData()
      setStatusMessage({
        text: `Added ${doc.supplier_name} invoice ${doc.invoice_number} directly into Engagement AP Ledger!`,
        type: 'success',
      })
    } catch (err: any) {
      alert(err.message)
    } finally {
      setLoading(false)
    }
  }

  const currentEngagement = engagements.find((e) => e.id === selectedEngId)

  // Calculations for dashboard
  const totalUsdVatAtRisk = engagements.reduce(
    (acc, curr) => acc + (curr.vat_at_risk_by_currency?.['USD'] || 0),
    0
  )
  const totalZwgVatAtRisk = engagements.reduce(
    (acc, curr) => acc + (curr.vat_at_risk_by_currency?.['ZWG'] || 0),
    0
  )
  const totalMatches = engagements.reduce((acc, curr) => acc + curr.matches_count, 0)
  const totalExceptions = engagements.reduce((acc, curr) => acc + curr.exceptions_count, 0)

  // Filtered exceptions
  const filteredExceptions = exceptions.filter((ex) => {
    if (filterClass === 'ALL') return true
    return ex.primary_class === filterClass
  })

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans text-slate-800">
      {/* --- Top Navigation Header --- */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-3 cursor-pointer" onClick={() => setActiveTab('dashboard')}>
              <div className="w-10 h-10 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-xl shadow-inner">
                F
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xl font-bold tracking-tight text-slate-900">FIRA</span>
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800">
                    Enterprise
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 font-medium leading-none">FDMS Input Tax Recovery Platform</p>
              </div>
            </div>

            {/* Navigation Tabs */}
            {currentUser && (
              <nav className="hidden md:flex items-center gap-1">
                <button
                  onClick={() => setActiveTab('dashboard')}
                  className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    activeTab === 'dashboard'
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`}
                >
                  Dashboard
                </button>
                <button
                  onClick={() => setActiveTab('clients')}
                  className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    activeTab === 'clients'
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`}
                >
                  Taxpayers & Clients
                </button>
                <button
                  onClick={() => setActiveTab('reconciliation')}
                  className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    activeTab === 'reconciliation'
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`}
                >
                  Reconciliation Workspace
                </button>
                <button
                  onClick={() => setActiveTab('letters')}
                  className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    activeTab === 'letters'
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`}
                >
                  Supplier Letters
                </button>
              </nav>
            )}
          </div>

          <div className="flex items-center gap-4">
            {/* Status Indicator */}
            <div className="flex items-center gap-2 border border-slate-200 bg-slate-50 px-2.5 py-1 rounded-full text-xs text-slate-600">
              <span className={`w-2 h-2 rounded-full ${apiOnline ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
              <span className="font-medium">{apiOnline ? 'Core API Online' : 'Offline'}</span>
            </div>

            {/* Auth Profile / Actions */}
            {currentUser ? (
              <div className="flex items-center gap-3">
                <div className="text-right hidden sm:block">
                  <p className="text-xs font-semibold text-slate-900">{currentUser.full_name}</p>
                  <p className="text-[10px] text-slate-500 uppercase tracking-wider font-mono">
                    {currentUser.role} • {currentUser.tenant_name}
                  </p>
                </div>
                <button
                  onClick={handleLogout}
                  title="Logout"
                  className="p-2 text-slate-500 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowLoginModal(true)}
                className="px-4 py-2 text-sm font-semibold text-white bg-blue-600 rounded-lg hover:bg-blue-700 shadow-sm"
              >
                Sign In
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Global Status Notification Toast */}
      {statusMessage && (
        <div
          className={`max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 mt-4 transition-all`}
        >
          <div
            className={`p-3 rounded-lg border text-sm flex items-center justify-between ${
              statusMessage.type === 'success'
                ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                : 'bg-rose-50 border-rose-200 text-rose-800'
            }`}
          >
            <div className="flex items-center gap-2">
              {statusMessage.type === 'success' ? <Check className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
              <span>{statusMessage.text}</span>
            </div>
            <button onClick={() => setStatusMessage(null)} className="text-xs font-bold hover:underline">
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* --- Main Workspace Views --- */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* ==================== VIEW 1: DASHBOARD ==================== */}
        {activeTab === 'dashboard' && (
          <div className="space-y-6">
            {/* Top Stats Banner */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
              <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm hover:shadow transition-shadow">
                <div className="flex items-center justify-between text-slate-500 mb-2">
                  <span className="text-xs font-semibold uppercase tracking-wider">VAT at Risk (USD)</span>
                  <div className="w-8 h-8 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center font-bold">
                    $
                  </div>
                </div>
                <div className="text-2xl font-bold text-slate-900">
                  ${totalUsdVatAtRisk.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <p className="text-xs text-rose-600 mt-1 font-medium flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5" /> Input tax subject to supplier correction
                </p>
              </div>

              <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm hover:shadow transition-shadow">
                <div className="flex items-center justify-between text-slate-500 mb-2">
                  <span className="text-xs font-semibold uppercase tracking-wider">VAT at Risk (ZWG)</span>
                  <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center font-bold text-xs">
                    ZWG
                  </div>
                </div>
                <div className="text-2xl font-bold text-slate-900">
                  ZWG {totalZwgVatAtRisk.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <p className="text-xs text-slate-500 mt-1">Segregated currency ledger (FR-VAL-4)</p>
              </div>

              <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm hover:shadow transition-shadow">
                <div className="flex items-center justify-between text-slate-500 mb-2">
                  <span className="text-xs font-semibold uppercase tracking-wider">Reconciled Matches</span>
                  <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                </div>
                <div className="text-2xl font-bold text-slate-900">{totalMatches}</div>
                <p className="text-xs text-emerald-600 mt-1 font-medium">Deterministic Passes P1-P5 validated</p>
              </div>

              <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm hover:shadow transition-shadow">
                <div className="flex items-center justify-between text-slate-500 mb-2">
                  <span className="text-xs font-semibold uppercase tracking-wider">Open Exceptions</span>
                  <Layers className="w-5 h-5 text-blue-500" />
                </div>
                <div className="text-2xl font-bold text-slate-900">{totalExceptions}</div>
                <p className="text-xs text-slate-500 mt-1">E1-E7 exception classes tracked</p>
              </div>
            </div>

            {/* --- Intelligent Scanned Document Auto-Recognition Banner --- */}
            <div className="bg-gradient-to-r from-blue-900 via-indigo-900 to-slate-900 rounded-2xl p-6 text-white shadow-lg border border-indigo-800/40 relative overflow-hidden">
              <div className="absolute right-0 top-0 translate-x-8 -translate-y-8 w-64 h-64 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />

              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 relative z-10">
                <div className="space-y-2 max-w-2xl">
                  <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/20 border border-blue-400/30 text-blue-300 text-xs font-semibold">
                    <Sparkles className="w-3.5 h-3.5 text-blue-400" /> Intelligent Document Ingestion & Company Auto-Recognition
                  </div>
                  <h2 className="text-xl font-bold tracking-tight text-white sm:text-2xl">
                    Drop Scanned Invoices — Zero Manual Company Setup
                  </h2>
                  <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                    No need to manually enter taxpayer details. Upload any scanned invoice, PDF, or purchase ledger. The system uses AI entity extraction to detect the Taxpayer Name, Zimbabwean TIN, VAT Category, and Currency, automatically onboarding the engagement with 1 click.
                  </p>

                  {/* 1-Click Demo Scanned Invoices */}
                  <div className="pt-2">
                    <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
                      ⚡ Or test with pre-packaged realistic Zimbabwean scanned invoices:
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => handleRecognizePreset('delta_beverages')}
                        disabled={isRecognizing}
                        className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 border border-white/10 text-xs font-medium text-white transition-all flex items-center gap-1.5 disabled:opacity-50"
                      >
                        <Sparkles className="w-3 h-3 text-emerald-400" /> Delta Corporation (USD $1,155)
                      </button>
                      <button
                        onClick={() => handleRecognizePreset('national_foods')}
                        disabled={isRecognizing}
                        className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 border border-white/10 text-xs font-medium text-white transition-all flex items-center gap-1.5 disabled:opacity-50"
                      >
                        <Sparkles className="w-3 h-3 text-amber-400" /> National Foods Holdings (USD $2,887.50)
                      </button>
                      <button
                        onClick={() => handleRecognizePreset('zesa_electricity')}
                        disabled={isRecognizing}
                        className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 border border-white/10 text-xs font-medium text-white transition-all flex items-center gap-1.5 disabled:opacity-50"
                      >
                        <Sparkles className="w-3 h-3 text-cyan-400" /> Olivine Industries (ZWG 17,325)
                      </button>
                      <button
                        onClick={() => handleRecognizePreset('econet_telecom')}
                        disabled={isRecognizing}
                        className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 border border-white/10 text-xs font-medium text-white transition-all flex items-center gap-1.5 disabled:opacity-50"
                      >
                        <Sparkles className="w-3 h-3 text-purple-400" /> Econet Telecom (USD $577.50)
                      </button>
                    </div>
                  </div>
                </div>

                {/* Upload Action Card */}
                <div className="bg-white/10 backdrop-blur-md p-5 rounded-xl border border-white/15 w-full lg:w-80 flex flex-col items-center justify-center text-center">
                  <label className="w-full cursor-pointer">
                    <input
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg,.xlsx,.csv,.txt"
                      onChange={handleRecognizeFile}
                      className="hidden"
                      disabled={isRecognizing}
                    />
                    <div className="border-2 border-dashed border-white/30 rounded-xl p-4 hover:border-blue-400 hover:bg-white/5 transition-all">
                      <Upload className="w-8 h-8 text-blue-300 mx-auto mb-2" />
                      <p className="text-xs font-bold text-white">Upload / Drop Scanned Invoice</p>
                      <p className="text-[10px] text-slate-300 mt-1">PDF, TIFF, PNG, or Excel Ledger</p>
                      <span className="mt-3 inline-block px-3 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-semibold transition-colors shadow">
                        {isRecognizing ? 'Extracting Layout...' : 'Browse Documents'}
                      </span>
                    </div>
                  </label>
                </div>
              </div>

              {/* Scanning Active Indicator */}
              {isRecognizing && (
                <div className="mt-4 p-4 rounded-xl bg-blue-950/80 border border-blue-500/30 flex items-center gap-3 animate-pulse">
                  <RefreshCw className="w-5 h-5 text-blue-400 animate-spin" />
                  <div>
                    <p className="text-xs font-bold text-blue-200">Analyzing Document Structure & Statutory Markers...</p>
                    <p className="text-[11px] text-slate-400">Extracting Buyer Name, Zimbabwean TIN, VAT Category, and Currency...</p>
                  </div>
                </div>
              )}

              {/* Error Banner */}
              {recognizeError && (
                <div className="mt-4 p-3 rounded-xl bg-rose-950/80 border border-rose-500/30 flex items-center justify-between text-rose-200 text-xs">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-rose-400" />
                    <span>{recognizeError}</span>
                  </div>
                  <button onClick={() => setRecognizeError(null)} className="font-bold hover:underline">Dismiss</button>
                </div>
              )}

              {/* Auto-Recognition Result Modal / Card */}
              {recognizedDoc && (
                <div className="mt-6 bg-slate-900/90 backdrop-blur-xl border-2 border-emerald-500/60 rounded-xl p-5 shadow-2xl">
                  <div className="flex flex-col md:flex-row md:items-center justify-between pb-4 border-b border-white/10 gap-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 flex items-center justify-center font-bold">
                        <CheckCircle2 className="w-6 h-6" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-white">Company Successfully Recognized!</span>
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/30 text-emerald-300 border border-emerald-500/40">
                            {recognizedDoc.confidence_score}% Confidence
                          </span>
                        </div>
                        <p className="text-xs text-slate-300">
                          {recognizedDoc.resolution.match_reason}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setRecognizedDoc(null)}
                        className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-xs font-semibold text-slate-300 transition-colors"
                      >
                        Dismiss
                      </button>
                      {selectedEngId && (
                        <button
                          onClick={() => handleIngestRecognizedInvoice(recognizedDoc)}
                          disabled={loading}
                          className="px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold transition-all shadow-md hover:shadow-blue-500/25 flex items-center gap-1.5"
                          title="Directly add this scanned invoice into active engagement AP ledger"
                        >
                          <Plus className="w-3.5 h-3.5" />
                          <span>➕ Ingest into AP Ledger</span>
                        </button>
                      )}
                      <button
                        onClick={() => handleAutoOnboardAndStart(recognizedDoc)}
                        disabled={loading}
                        className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-all shadow-md hover:shadow-emerald-500/25 flex items-center gap-2"
                      >
                        <Sparkles className="w-4 h-4" />
                        🚀 1-Click Launch Reconciliation for {recognizedDoc.buyer_name}
                      </button>
                    </div>
                  </div>

                  {/* Extracted Metadata Grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mt-4 text-xs">
                    <div className="bg-white/5 p-3 rounded-lg border border-white/10">
                      <span className="text-[10px] uppercase font-bold text-slate-400">Recognized Taxpayer</span>
                      <p className="font-bold text-white truncate mt-0.5">{recognizedDoc.buyer_name}</p>
                    </div>

                    <div className="bg-white/5 p-3 rounded-lg border border-white/10">
                      <span className="text-[10px] uppercase font-bold text-slate-400">Zimbabwean TIN</span>
                      <p className="font-mono font-bold text-emerald-300 mt-0.5">{recognizedDoc.buyer_tin}</p>
                    </div>

                    <div className="bg-white/5 p-3 rounded-lg border border-white/10">
                      <span className="text-[10px] uppercase font-bold text-slate-400">Supplier Counterparty</span>
                      <p className="font-bold text-white truncate mt-0.5">{recognizedDoc.supplier_name}</p>
                    </div>

                    <div className="bg-white/5 p-3 rounded-lg border border-white/10">
                      <span className="text-[10px] uppercase font-bold text-slate-400">Invoice Number</span>
                      <p className="font-mono font-bold text-blue-300 mt-0.5">{recognizedDoc.invoice_number}</p>
                    </div>

                    <div className="bg-white/5 p-3 rounded-lg border border-white/10">
                      <span className="text-[10px] uppercase font-bold text-slate-400">Gross / VAT</span>
                      <p className="font-mono font-bold text-white mt-0.5">
                        {recognizedDoc.currency} {recognizedDoc.gross_amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        <span className="text-slate-400 text-[10px] block font-normal">VAT: {recognizedDoc.currency} {recognizedDoc.vat_amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                      </p>
                    </div>

                    <div className="bg-white/5 p-3 rounded-lg border border-white/10">
                      <span className="text-[10px] uppercase font-bold text-slate-400">Client Status</span>
                      <p className="mt-0.5">
                        {recognizedDoc.resolution.status === 'matched_existing' ? (
                          <span className="text-emerald-400 font-bold">● Linked to Client</span>
                        ) : (
                          <span className="text-amber-400 font-bold">✨ Ready to Auto-Create</span>
                        )}
                      </p>
                    </div>
                  </div>

                  {/* Real-Time Statutory & Fiscal Verification Panel (Option A) */}
                  <div className="mt-5 pt-4 border-t border-white/10">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-md bg-blue-500/20 text-blue-400 flex items-center justify-center">
                          <Cpu className="w-3.5 h-3.5" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-white uppercase tracking-wider">
                              ⚡ Real-Time Statutory & Fiscal Checklist
                            </span>
                            {recognizedDoc.realtime_validation?.is_statutory_valid ? (
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                                ✓ Statutory Valid Tax Invoice
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                                ⚠️ Statutory Review Advised
                              </span>
                            )}
                          </div>
                          <p className="text-[11px] text-slate-400">
                            Instant local statutory rules verification + 1-click official ZIMRA portal certificate lookup
                          </p>
                        </div>
                      </div>

                      {/* 1-Click Official ZIMRA Portal Verification Button */}
                      <a
                        href={recognizedDoc.zimra_portal_url || `https://fdms.zimra.co.zw/verify?tin=${recognizedDoc.supplier_tin}&inv=${recognizedDoc.invoice_number}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold transition-all shadow-md hover:shadow-blue-500/25 shrink-0"
                        title="Opens official ZIMRA FDMS portal in a new tab to inspect live fiscal certificate"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                        <span>🔍 Verify on Official ZIMRA Portal ↗</span>
                      </a>
                    </div>

                    {/* Fiscal Markers Bar (Device, Day, Code) */}
                    {(recognizedDoc.fiscal_details?.device_serial || recognizedDoc.fiscal_details?.verification_code) && (
                      <div className="mb-3 py-1.5 px-3 rounded-lg bg-white/5 border border-white/10 flex flex-wrap items-center gap-4 text-[11px] text-slate-300 font-mono">
                        {recognizedDoc.fiscal_details?.device_serial && (
                          <div>
                            <span className="text-slate-500 uppercase mr-1">Fiscal Device:</span>
                            <span className="text-emerald-300 font-bold">{recognizedDoc.fiscal_details.device_serial}</span>
                          </div>
                        )}
                        {recognizedDoc.fiscal_details?.fiscal_day && (
                          <div>
                            <span className="text-slate-500 uppercase mr-1">Fiscal Day:</span>
                            <span className="text-blue-300 font-bold">{recognizedDoc.fiscal_details.fiscal_day}</span>
                          </div>
                        )}
                        {recognizedDoc.fiscal_details?.verification_code && (
                          <div>
                            <span className="text-slate-500 uppercase mr-1">Code / Hash:</span>
                            <span className="text-amber-300 font-bold">{recognizedDoc.fiscal_details.verification_code}</span>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Dynamic Rule Checks Grid */}
                    {recognizedDoc.realtime_validation?.checks && (
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                        {recognizedDoc.realtime_validation.checks.map((check, idx) => {
                          const isPass = check.status === 'PASS'
                          const isWarn = check.status === 'WARN'
                          const isFail = check.status === 'FAIL'
                          const isInfo = check.status === 'INFO'

                          return (
                            <div
                              key={idx}
                              className={`p-2.5 rounded-lg border text-xs flex items-start gap-2.5 ${
                                isPass
                                  ? 'bg-emerald-950/30 border-emerald-500/30 text-emerald-200'
                                  : isWarn
                                  ? 'bg-amber-950/30 border-amber-500/30 text-amber-200'
                                  : isFail
                                  ? 'bg-rose-950/30 border-rose-500/30 text-rose-200'
                                  : 'bg-blue-950/30 border-blue-500/30 text-blue-200'
                              }`}
                            >
                              <div className="mt-0.5 shrink-0">
                                {isPass && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
                                {isWarn && <AlertTriangle className="w-4 h-4 text-amber-400" />}
                                {isFail && <XCircle className="w-4 h-4 text-rose-400" />}
                                {isInfo && <Info className="w-4 h-4 text-blue-400" />}
                              </div>
                              <div className="min-w-0">
                                <p className="font-bold text-white text-[11px] leading-tight">{check.name}</p>
                                <p className="text-[10px] text-slate-300 leading-snug mt-0.5">{check.details}</p>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Engagements Section */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-100 gap-4">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">Tax Recovery Engagements</h2>
                  <p className="text-xs text-slate-500">
                    Accounts payable reconciliation reviews against ZIMRA Fiscal Data Management System records.
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setShowNewEngModal(true)}
                    className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700 shadow-sm transition-colors"
                  >
                    <Plus className="w-4 h-4" /> New Engagement
                  </button>
                </div>
              </div>

              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                    <tr>
                      <th className="py-3 px-4">Reference</th>
                      <th className="py-3 px-4">Taxpayer Client</th>
                      <th className="py-3 px-4">Period</th>
                      <th className="py-3 px-4">Lines (AP / ZIMRA)</th>
                      <th className="py-3 px-4">Matches</th>
                      <th className="py-3 px-4">VAT at Risk</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {engagements.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="py-8 text-center text-slate-400">
                          No engagements registered yet. Click &quot;New Engagement&quot; to begin.
                        </td>
                      </tr>
                    ) : (
                      engagements.map((eng) => (
                        <tr key={eng.id} className="hover:bg-slate-50/80 transition-colors">
                          <td className="py-3 px-4 font-mono font-bold text-blue-600">{eng.reference}</td>
                          <td className="py-3 px-4 font-semibold text-slate-900">
                            {eng.client_name}
                            <span className="block text-[10px] text-slate-400 font-mono font-normal">
                              TIN: {eng.client_tin}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-slate-600">
                            {eng.period_start} → {eng.period_end}
                          </td>
                          <td className="py-3 px-4 font-mono">
                            <span className="text-slate-900 font-semibold">{eng.ap_lines_count}</span> AP /{' '}
                            <span className="text-slate-900 font-semibold">{eng.zimra_lines_count}</span> ZIMRA
                          </td>
                          <td className="py-3 px-4 font-semibold text-emerald-600">
                            {eng.matches_count} matched
                          </td>
                          <td className="py-3 px-4 font-mono font-semibold text-rose-600">
                            {eng.vat_at_risk_by_currency?.['USD'] ? `$${eng.vat_at_risk_by_currency['USD'].toLocaleString()}` : '$0.00'}
                            {eng.vat_at_risk_by_currency?.['ZWG'] ? ` + ZWG ${eng.vat_at_risk_by_currency['ZWG'].toLocaleString()}` : ''}
                          </td>
                          <td className="py-3 px-4">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                                eng.status === 'REVIEW'
                                  ? 'bg-amber-100 text-amber-800'
                                  : eng.status === 'INGESTING'
                                  ? 'bg-blue-100 text-blue-800'
                                  : 'bg-slate-100 text-slate-700'
                              }`}
                            >
                              {eng.status}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <button
                              onClick={() => {
                                setSelectedEngId(eng.id)
                                setActiveTab('reconciliation')
                              }}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-100 text-slate-700 hover:bg-blue-50 hover:text-blue-700 font-semibold text-xs transition-colors"
                            >
                              Workspace <ArrowRight className="w-3.5 h-3.5" />
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ==================== VIEW 2: CLIENTS ==================== */}
        {activeTab === 'clients' && (
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-100 gap-4">
              <div>
                <h2 className="text-lg font-bold text-slate-900">Taxpayer Business Units</h2>
                <p className="text-xs text-slate-500">
                  Registered Zimbabwean taxpayer clients with validated Tax Identification Numbers (TINs).
                </p>
              </div>
              <button
                onClick={() => setShowNewClientModal(true)}
                className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700 shadow-sm"
              >
                <Plus className="w-4 h-4" /> Register Client
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                  <tr>
                    <th className="py-3 px-4">Legal Name</th>
                    <th className="py-3 px-4">Trading Name</th>
                    <th className="py-3 px-4">TIN</th>
                    <th className="py-3 px-4">VAT Category</th>
                    <th className="py-3 px-4">Currency</th>
                    <th className="py-3 px-4">City</th>
                    <th className="py-3 px-4">Contact</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {clients.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-slate-400">
                        No clients registered. Click &quot;Register Client&quot; to add your first taxpayer unit.
                      </td>
                    </tr>
                  ) : (
                    clients.map((c) => (
                      <tr key={c.id} className="hover:bg-slate-50/80">
                        <td className="py-3 px-4 font-bold text-slate-900">{c.legal_name}</td>
                        <td className="py-3 px-4 text-slate-600">{c.trading_name || '—'}</td>
                        <td className="py-3 px-4 font-mono font-semibold text-blue-600">{c.tin_normalised}</td>
                        <td className="py-3 px-4">
                          <span className="px-2 py-0.5 rounded bg-slate-100 font-mono font-bold text-slate-700">
                            Category {c.vat_category}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-semibold">{c.default_currency}</td>
                        <td className="py-3 px-4 text-slate-600">{c.city || 'Harare'}</td>
                        <td className="py-3 px-4 text-slate-600">{c.contact_email || '—'}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ==================== VIEW 3: RECONCILIATION WORKSPACE ==================== */}
        {activeTab === 'reconciliation' && (
          <div className="space-y-6">
            {/* Engagement Selection Bar */}
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center font-bold">
                  <Layers className="w-5 h-5" />
                </div>
                <div>
                  <label htmlFor="engagement-selector" className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    Active Engagement Workspace
                  </label>
                  <div className="flex items-center gap-3 mt-0.5">
                    <select
                      id="engagement-selector"
                      value={selectedEngId}
                      onChange={(e) => setSelectedEngId(e.target.value)}
                      className="text-sm font-bold text-slate-900 bg-transparent border-none p-0 focus:ring-0 cursor-pointer"
                    >
                      {engagements.map((eng) => (
                        <option key={eng.id} value={eng.id}>
                          {eng.reference} — {eng.client_name} ({eng.period_start} to {eng.period_end})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              {/* Step Navigation Pill */}
              <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg text-xs font-semibold text-slate-600 self-start md:self-auto">
                <button
                  onClick={() => setReconcileStep(1)}
                  className={`px-3 py-1.5 rounded-md transition-colors ${
                    reconcileStep === 1 ? 'bg-white text-blue-600 shadow-sm' : 'hover:text-slate-900'
                  }`}
                >
                  1. Ingestion
                </button>
                <button
                  onClick={() => setReconcileStep(2)}
                  className={`px-3 py-1.5 rounded-md transition-colors ${
                    reconcileStep === 2 ? 'bg-white text-blue-600 shadow-sm' : 'hover:text-slate-900'
                  }`}
                >
                  2. Engine Run
                </button>
                <button
                  onClick={() => setReconcileStep(3)}
                  className={`px-3 py-1.5 rounded-md transition-colors ${
                    reconcileStep === 3 ? 'bg-white text-blue-600 shadow-sm' : 'hover:text-slate-900'
                  }`}
                >
                  3. Matches ({matches.length})
                </button>
                <button
                  onClick={() => setReconcileStep(4)}
                  className={`px-3 py-1.5 rounded-md transition-colors ${
                    reconcileStep === 4 ? 'bg-white text-blue-600 shadow-sm' : 'hover:text-slate-900'
                  }`}
                >
                  4. Exceptions ({exceptions.length})
                </button>
              </div>
            </div>

            {/* STEP 1: FILE INGESTION */}
            {reconcileStep === 1 && (
              <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* AP Ledger Ingestion Card */}
                  <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                          <FileSpreadsheet className="w-5 h-5" />
                        </div>
                        <div>
                          <h3 className="font-bold text-slate-900 text-sm">AP Purchase Ledger File</h3>
                          <p className="text-xs text-slate-500">Client internal accounting records</p>
                        </div>
                      </div>
                      <span className="text-xs font-mono font-bold px-2 py-1 bg-indigo-50 text-indigo-700 rounded">
                        {currentEngagement?.ap_lines_count || 0} Lines Loaded
                      </span>
                    </div>

                    <label className="border-2 border-dashed border-slate-200 rounded-lg p-6 text-center hover:border-blue-400 transition-colors cursor-pointer bg-slate-50/50 block relative">
                      <input
                        type="file"
                        accept=".xlsx,.xls,.csv"
                        onChange={handleUploadApFile}
                        disabled={isUploadingAp || !selectedEngId}
                        className="hidden"
                      />
                      {isUploadingAp ? (
                        <div className="flex flex-col items-center gap-2">
                          <RefreshCw className="w-7 h-7 text-blue-500 animate-spin" />
                          <p className="text-xs font-semibold text-blue-700">Ingesting AP Purchase Ledger...</p>
                        </div>
                      ) : (
                        <div>
                          <Upload className="w-7 h-7 text-slate-400 mx-auto mb-2" />
                          <p className="text-xs font-semibold text-slate-700">Click to upload Purchase Ledger</p>
                          <p className="text-[11px] text-slate-400 mt-1">Supports .xlsx, .xls, and .csv (max 25MB)</p>
                        </div>
                      )}
                    </label>
                  </div>

                  {/* ZIMRA Claim List Ingestion Card */}
                  <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                          <ShieldCheck className="w-5 h-5" />
                        </div>
                        <div>
                          <h3 className="font-bold text-slate-900 text-sm">ZIMRA Claim List Export</h3>
                          <p className="text-xs text-slate-500">FDMS gateway exported invoices (HC-1, HC-2)</p>
                        </div>
                      </div>
                      <span className="text-xs font-mono font-bold px-2 py-1 bg-emerald-50 text-emerald-700 rounded">
                        {currentEngagement?.zimra_lines_count || 0} Lines Loaded
                      </span>
                    </div>

                    <label className="border-2 border-dashed border-slate-200 rounded-lg p-6 text-center hover:border-emerald-400 transition-colors cursor-pointer bg-slate-50/50 block relative">
                      <input
                        type="file"
                        accept=".xlsx,.xls,.csv"
                        onChange={handleUploadZimraFile}
                        disabled={isUploadingZimra || !selectedEngId}
                        className="hidden"
                      />
                      {isUploadingZimra ? (
                        <div className="flex flex-col items-center gap-2">
                          <RefreshCw className="w-7 h-7 text-emerald-500 animate-spin" />
                          <p className="text-xs font-semibold text-emerald-700">Ingesting ZIMRA FDMS Claim Export...</p>
                        </div>
                      ) : (
                        <div>
                          <Upload className="w-7 h-7 text-slate-400 mx-auto mb-2" />
                          <p className="text-xs font-semibold text-slate-700">Click to upload ZIMRA Export</p>
                          <p className="text-[11px] text-slate-400 mt-1">Manual taxpayer export only (No live scraping)</p>
                        </div>
                      )}
                    </label>
                  </div>
                </div>

                {/* Instant Sample Data Loader */}
                <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-xl p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-blue-600" />
                      <h4 className="font-bold text-slate-900 text-sm">Instant Demo Data Generator</h4>
                    </div>
                    <p className="text-xs text-slate-600 max-w-2xl">
                      Populate authentic Zimbabwean taxpayer records (Delta Beverages, Econet, National Foods, Olivine, Simbisa, Zimplats, and ZESA) to immediately test P1-P5 matching passes and E1-E7 exception detection.
                    </p>
                  </div>
                  <button
                    onClick={handleSeedSampleData}
                    disabled={loading}
                    className="px-4 py-2.5 rounded-lg bg-blue-600 text-white font-semibold text-xs hover:bg-blue-700 shadow-sm flex items-center gap-2 whitespace-nowrap transition-colors"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Load Sample Datasets
                  </button>
                </div>
              </div>
            )}

            {/* STEP 2: ENGINE EXECUTION */}
            {reconcileStep === 2 && (
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-8 text-center max-w-2xl mx-auto space-y-6">
                <div className="w-16 h-16 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center mx-auto">
                  <Play className="w-8 h-8 ml-1" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-900">Execute Deterministic Reconciliation</h3>
                  <p className="text-xs text-slate-500 mt-1">
                    Runs multi-pass matching passes P1-P5 and categorizes VAT-at-risk exceptions E1-E7.
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-4 text-left p-4 bg-slate-50 rounded-lg text-xs">
                  <div>
                    <span className="text-slate-400">AP Ledger Lines:</span>
                    <p className="font-bold text-slate-900 text-sm">{currentEngagement?.ap_lines_count || 0}</p>
                  </div>
                  <div>
                    <span className="text-slate-400">ZIMRA Fiscal Lines:</span>
                    <p className="font-bold text-slate-900 text-sm">{currentEngagement?.zimra_lines_count || 0}</p>
                  </div>
                  <div>
                    <span className="text-slate-400">Matching Mode:</span>
                    <p className="font-bold text-slate-900">Deterministic (HC-4)</p>
                  </div>
                  <div>
                    <span className="text-slate-400">VAT Rate Engine:</span>
                    <p className="font-bold text-slate-900">Date-resolved (HC-3)</p>
                  </div>
                </div>

                <button
                  onClick={handleRunReconciliation}
                  disabled={loading || (currentEngagement?.ap_lines_count || 0) === 0}
                  className="w-full py-3 rounded-lg bg-blue-600 text-white font-bold text-sm hover:bg-blue-700 shadow-sm transition-colors flex items-center justify-center gap-2"
                >
                  <Play className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                  {loading ? 'Running Multi-Pass Matching...' : 'Run Reconciliation Engine'}
                </button>
              </div>
            )}

            {/* STEP 3: MATCHES TABLE */}
            {reconcileStep === 3 && (
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-100 gap-4">
                  <div>
                    <h3 className="text-base font-bold text-slate-900">Reconciled Invoice Matches ({matches.length})</h3>
                    <p className="text-xs text-slate-500">
                      Lines aligned between AP ledger and ZIMRA through deterministic passes P1-P5.
                    </p>
                  </div>
                  <button
                    onClick={() => setReconcileStep(4)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-rose-50 text-rose-700 rounded-lg text-xs font-semibold hover:bg-rose-100 transition-colors"
                  >
                    View Exceptions ({exceptions.length}) <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                      <tr>
                        <th className="py-3 px-4">Pass ID</th>
                        <th className="py-3 px-4">Confidence</th>
                        <th className="py-3 px-4">Supplier Name</th>
                        <th className="py-3 px-4">Invoice #</th>
                        <th className="py-3 px-4">Date</th>
                        <th className="py-3 px-4">Currency</th>
                        <th className="py-3 px-4">AP Gross</th>
                        <th className="py-3 px-4">ZIMRA Gross</th>
                        <th className="py-3 px-4">AP VAT</th>
                        <th className="py-3 px-4">ZIMRA VAT</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {matches.map((m) => (
                        <tr key={m.id} className="hover:bg-slate-50/80">
                          <td className="py-3 px-4">
                            <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 font-mono font-bold">
                              {m.pass_id}
                            </span>
                          </td>
                          <td className="py-3 px-4 font-bold text-emerald-600">{m.confidence}%</td>
                          <td className="py-3 px-4 font-semibold text-slate-900">{m.supplier_name}</td>
                          <td className="py-3 px-4 font-mono">{m.invoice_number}</td>
                          <td className="py-3 px-4 text-slate-500">{m.invoice_date}</td>
                          <td className="py-3 px-4 font-semibold">{m.currency}</td>
                          <td className="py-3 px-4 font-mono font-semibold">${m.ap_gross.toFixed(2)}</td>
                          <td className="py-3 px-4 font-mono font-semibold">${m.zimra_gross.toFixed(2)}</td>
                          <td className="py-3 px-4 font-mono text-slate-600">${m.ap_vat.toFixed(2)}</td>
                          <td className="py-3 px-4 font-mono text-slate-600">${m.zimra_vat.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* STEP 4: EXCEPTION REGISTER (E1-E7) */}
            {reconcileStep === 4 && (
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-100 gap-4">
                  <div>
                    <h3 className="text-base font-bold text-slate-900">VAT-at-Risk Exception Register</h3>
                    <p className="text-xs text-slate-500">
                      Non-claimable VAT classified across statutory exception rules E1 through E7.
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <label htmlFor="filter-class-select" className="text-xs text-slate-500">Filter Class:</label>
                    <select
                      id="filter-class-select"
                      value={filterClass}
                      onChange={(e) => setFilterClass(e.target.value)}
                      className="text-xs border border-slate-200 rounded-md px-2 py-1 font-semibold"
                    >
                      <option value="ALL">All Exception Classes</option>
                      <option value="E1">E1: Absent from ZIMRA</option>
                      <option value="E2">E2: Buyer TIN Mismatch</option>
                      <option value="E3">E3: Buyer Particulars Mismatch</option>
                      <option value="E4">E4: Marked Not Valid</option>
                      <option value="E5">E5: Value / Rate Discrepancy</option>
                      <option value="E6">E6: Unlinked Credit Note</option>
                      <option value="E7">E7: Non-qualifying Expense</option>
                    </select>

                    <button
                      onClick={() => setActiveTab('letters')}
                      className="ml-3 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-semibold hover:bg-blue-700"
                    >
                      Draft Letters
                    </button>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                      <tr>
                        <th className="py-3 px-4">Class</th>
                        <th className="py-3 px-4">Rule ID</th>
                        <th className="py-3 px-4">Supplier</th>
                        <th className="py-3 px-4">Invoice #</th>
                        <th className="py-3 px-4">Date</th>
                        <th className="py-3 px-4">VAT at Risk</th>
                        <th className="py-3 px-4">Nature</th>
                        <th className="py-3 px-4">Status</th>
                        <th className="py-3 px-4 text-right">Evidence</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {filteredExceptions.map((ex) => (
                        <tr key={ex.id} className="hover:bg-slate-50/80">
                          <td className="py-3 px-4 font-mono font-bold text-rose-600">
                            <span className="px-2 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-100">
                              {ex.primary_class}
                            </span>
                          </td>
                          <td className="py-3 px-4 font-mono text-slate-500">{ex.rule_id}</td>
                          <td className="py-3 px-4 font-semibold text-slate-900">{ex.supplier_name}</td>
                          <td className="py-3 px-4 font-mono">{ex.invoice_number}</td>
                          <td className="py-3 px-4 text-slate-500">{ex.invoice_date}</td>
                          <td className="py-3 px-4 font-mono font-bold text-rose-600">
                            {ex.currency} ${ex.vat_at_risk.toFixed(2)}
                          </td>
                          <td className="py-3 px-4">
                            {ex.is_advisory ? (
                              <span className="px-2 py-0.5 rounded bg-amber-100 text-amber-800 text-[10px] font-bold">
                                Advisory
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded bg-rose-100 text-rose-800 text-[10px] font-bold">
                                At Risk
                              </span>
                            )}
                          </td>
                          <td className="py-3 px-4">
                            <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-[10px] font-semibold">
                              {ex.status}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <button
                              onClick={() => setActiveEvidenceModal(ex)}
                              className="p-1 text-slate-400 hover:text-blue-600 rounded transition-colors"
                              title="View Evidence JSON"
                            >
                              <Eye className="w-4 h-4 inline" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ==================== VIEW 4: SUPPLIER CORRECTION LETTERS ==================== */}
        {activeTab === 'letters' && (
          <div className="space-y-6">
            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-100 gap-4">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">Supplier VAT Correction Notices</h2>
                  <p className="text-xs text-slate-500">
                    Generate statutory tax invoice correction letters under Section 15(2) of the Zimbabwe VAT Act.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                {/* Supplier List */}
                <div className="md:col-span-1 border border-slate-200 rounded-lg p-4 space-y-3 bg-slate-50/50">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                    Suppliers with Unclaimable VAT ({suppliers.length})
                  </h4>
                  <div className="space-y-2">
                    {suppliers.length === 0 ? (
                      <p className="text-xs text-slate-400 py-4">No suppliers with open exceptions found.</p>
                    ) : (
                      suppliers.map((s, idx) => (
                        <div
                          key={idx}
                          onClick={() => handleGenerateLetter(s)}
                          className={`p-3 rounded-lg border cursor-pointer transition-all ${
                            selectedSupplierForLetter?.supplier_name === s.supplier_name
                              ? 'bg-blue-50 border-blue-300 shadow-sm'
                              : 'bg-white border-slate-200 hover:border-slate-300'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <p className="text-xs font-bold text-slate-900">{s.supplier_name}</p>
                            <span className="text-xs font-mono font-bold text-rose-600">
                              ${s.total_vat_at_risk.toFixed(2)}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-500 mt-1 font-mono">TIN: {s.supplier_tin}</p>
                          <p className="text-[11px] text-slate-400">{s.exception_count} affected invoice(s)</p>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                {/* Letter Preview Display */}
                <div className="md:col-span-2 border border-slate-200 rounded-lg p-6 bg-white flex flex-col space-y-4">
                  {generatedLetter ? (
                    <>
                      <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                        <div>
                          <span className="text-xs font-mono text-blue-600 font-bold">
                            REF: {generatedLetter.letter_ref}
                          </span>
                          <h3 className="text-sm font-bold text-slate-900">{generatedLetter.supplier_name}</h3>
                        </div>
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(generatedLetter.letter_text)
                            setCopiedLetter(true)
                            setTimeout(() => setCopiedLetter(false), 2000)
                          }}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                        >
                          {copiedLetter ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                          {copiedLetter ? 'Copied to Clipboard' : 'Copy Notice Text'}
                        </button>
                      </div>

                      <pre className="flex-1 bg-slate-50 border border-slate-100 rounded-lg p-4 text-xs font-mono text-slate-800 whitespace-pre-wrap leading-relaxed overflow-y-auto max-h-[450px]">
                        {generatedLetter.letter_text}
                      </pre>
                    </>
                  ) : (
                    <div className="flex-1 flex flex-col items-center justify-center text-center py-16 text-slate-400">
                      <Send className="w-10 h-10 mb-2 opacity-30" />
                      <p className="text-sm font-semibold text-slate-600">Select a supplier to generate formal letter draft</p>
                      <p className="text-xs max-w-sm mt-1">
                        Notice will automatically include the affected invoice numbers, dates, gross values, and VAT at risk.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* --- Evidence Drawer Modal --- */}
      {activeEvidenceModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-lg w-full p-6 shadow-xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="font-bold text-slate-900 text-sm">
                Exception Evidence: {activeEvidenceModal.primary_class} ({activeEvidenceModal.rule_id})
              </h3>
              <button
                onClick={() => setActiveEvidenceModal(null)}
                className="text-slate-400 hover:text-slate-600 font-bold"
              >
                ✕
              </button>
            </div>
            <div className="text-xs space-y-2">
              <p>
                <span className="font-semibold text-slate-700">Supplier:</span> {activeEvidenceModal.supplier_name}
              </p>
              <p>
                <span className="font-semibold text-slate-700">Invoice:</span> {activeEvidenceModal.invoice_number} (
                {activeEvidenceModal.invoice_date})
              </p>
              <p>
                <span className="font-semibold text-slate-700">VAT at Risk:</span>{' '}
                <span className="font-bold text-rose-600">${activeEvidenceModal.vat_at_risk.toFixed(2)}</span>
              </p>
            </div>
            <div>
              <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1">Evidence JSON:</p>
              <pre className="bg-slate-50 border border-slate-200 rounded p-3 text-[11px] font-mono overflow-auto max-h-48 text-slate-800">
                {JSON.stringify(activeEvidenceModal.evidence, null, 2)}
              </pre>
            </div>

            {/* 1-Click Official ZIMRA Portal Lookup for Exception Invoice */}
            <a
              href={`https://fdms.zimra.co.zw/verify?inv=${encodeURIComponent(activeEvidenceModal.invoice_number)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 w-full py-2 bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200 font-semibold rounded-lg text-xs transition-colors shadow-sm"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>🔍 Verify Invoice {activeEvidenceModal.invoice_number} on Official ZIMRA Portal ↗</span>
            </a>

            <button
              onClick={() => setActiveEvidenceModal(null)}
              className="w-full py-2 bg-slate-100 text-slate-700 font-semibold rounded-lg text-xs hover:bg-slate-200"
            >
              Close
            </button>
          </div>
        </div>
      )}

      {/* --- New Client Modal --- */}
      {showNewClientModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-md w-full p-6 shadow-xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h3 className="font-bold text-slate-900 text-sm">Register Taxpayer Business Unit</h3>
              <button onClick={() => setShowNewClientModal(false)} className="text-slate-400 hover:text-slate-600">
                ✕
              </button>
            </div>

            {clientFormError && (
              <div className="p-2.5 bg-rose-50 border border-rose-200 text-rose-700 rounded text-xs">
                {clientFormError}
              </div>
            )}

            <form onSubmit={handleCreateClient} className="space-y-3 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Legal Business Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Delta Corporation Limited"
                  value={newClientForm.legal_name}
                  onChange={(e) => setNewClientForm({ ...newClientForm, legal_name: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Trading Name (Optional)</label>
                <input
                  type="text"
                  placeholder="e.g. Delta Beverages"
                  value={newClientForm.trading_name}
                  onChange={(e) => setNewClientForm({ ...newClientForm, trading_name: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">
                  Tax Identification Number (TIN) *
                </label>
                <input
                  type="text"
                  required
                  placeholder="9 or 10 numeric digits (e.g. 2000123456)"
                  value={newClientForm.tin_raw}
                  onChange={(e) => setNewClientForm({ ...newClientForm, tin_raw: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg font-mono focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-[10px] text-slate-400 mt-1">Must strictly match Zimbabwean regex: ^\d{'{9,10}'}$</p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">VAT Category</label>
                  <select
                    value={newClientForm.vat_category}
                    onChange={(e) => setNewClientForm({ ...newClientForm, vat_category: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                  >
                    <option value="A">Category A</option>
                    <option value="B">Category B</option>
                    <option value="C">Category C (Monthly)</option>
                    <option value="D">Category D</option>
                  </select>
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Default Currency</label>
                  <select
                    value={newClientForm.default_currency}
                    onChange={(e) => setNewClientForm({ ...newClientForm, default_currency: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg font-bold"
                  >
                    <option value="USD">USD ($)</option>
                    <option value="ZWG">ZWG</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Contact Email</label>
                <input
                  type="email"
                  placeholder="tax@taxpayer.co.zw"
                  value={newClientForm.contact_email}
                  onChange={(e) => setNewClientForm({ ...newClientForm, contact_email: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowNewClientModal(false)}
                  className="px-3 py-2 rounded-lg border border-slate-200 text-slate-600 font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700"
                >
                  Register Client
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* --- New Engagement Modal --- */}
      {showNewEngModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-md w-full p-6 shadow-xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h3 className="font-bold text-slate-900 text-sm">Create Reconciliation Engagement</h3>
              <button onClick={() => setShowNewEngModal(false)} className="text-slate-400 hover:text-slate-600">
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateEngagement} className="space-y-3 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Taxpayer Client *</label>
                <select
                  required
                  value={newEngForm.client_id}
                  onChange={(e) => setNewEngForm({ ...newEngForm, client_id: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                >
                  {clients.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.legal_name} (TIN: {c.tin_normalised})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Engagement Reference *</label>
                <input
                  type="text"
                  required
                  value={newEngForm.reference}
                  onChange={(e) => setNewEngForm({ ...newEngForm, reference: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg font-mono font-bold"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Period Start</label>
                  <input
                    type="date"
                    required
                    value={newEngForm.period_start}
                    onChange={(e) => setNewEngForm({ ...newEngForm, period_start: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Period End</label>
                  <input
                    type="date"
                    required
                    value={newEngForm.period_end}
                    onChange={(e) => setNewEngForm({ ...newEngForm, period_end: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                  />
                </div>
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Reporting Currency</label>
                <select
                  value={newEngForm.currency}
                  onChange={(e) => setNewEngForm({ ...newEngForm, currency: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg font-bold"
                >
                  <option value="USD">USD — US Dollar</option>
                  <option value="ZWG">ZWG — Zimbabwe Gold</option>
                </select>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowNewEngModal(false)}
                  className="px-3 py-2 rounded-lg border border-slate-200 text-slate-600 font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700"
                >
                  Create Engagement
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* --- Enterprise Authentication Modal --- */}
      {showLoginModal && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-8 shadow-2xl border border-slate-200 space-y-6">
            <div className="text-center space-y-1">
              <div className="w-12 h-12 rounded-xl bg-blue-600 text-white flex items-center justify-center font-bold text-2xl mx-auto shadow-md">
                F
              </div>
              <h3 className="text-xl font-bold text-slate-900 pt-2">FIRA Enterprise Sign In</h3>
              <p className="text-xs text-slate-500">
                NIST SP 800-63B Authentication & Role-Based Access Control
              </p>
            </div>

            {authError && (
              <div className="p-3 bg-rose-50 border border-rose-200 text-rose-700 rounded-lg text-xs flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>{authError}</span>
              </div>
            )}

            <form onSubmit={handleLogin} className="space-y-4 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Corporate Email Address</label>
                <input
                  type="email"
                  required
                  value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)}
                  className="w-full px-3 py-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Password</label>
                <input
                  type="password"
                  required
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  className="w-full px-3 py-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">
                  TOTP Code (Only if MFA Enabled)
                </label>
                <input
                  type="text"
                  placeholder="6-digit code e.g. 123456"
                  maxLength={6}
                  value={loginMfa}
                  onChange={(e) => setLoginMfa(e.target.value)}
                  className="w-full px-3 py-2.5 border border-slate-300 rounded-lg font-mono text-center tracking-widest"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 rounded-lg bg-blue-600 text-white font-bold hover:bg-blue-700 shadow-md transition-colors"
              >
                {loading ? 'Authenticating...' : 'Sign In to Workspace'}
              </button>
            </form>

            {/* Quick Demo Role Switcher */}
            <div className="pt-2 border-t border-slate-100">
              <p className="text-[11px] font-semibold text-slate-400 text-center uppercase tracking-wider mb-2">
                Quick Demo Role Switcher
              </p>
              <div className="grid grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={() => handleQuickDemoLogin('admin@fira.local')}
                  className="py-1.5 px-2 rounded border border-slate-200 text-[11px] font-semibold text-slate-700 hover:bg-blue-50 hover:text-blue-700"
                >
                  Admin
                </button>
                <button
                  type="button"
                  onClick={() => handleQuickDemoLogin('reviewer@fira.local')}
                  className="py-1.5 px-2 rounded border border-slate-200 text-[11px] font-semibold text-slate-700 hover:bg-blue-50 hover:text-blue-700"
                >
                  Reviewer
                </button>
                <button
                  type="button"
                  onClick={() => handleQuickDemoLogin('operator@fira.local')}
                  className="py-1.5 px-2 rounded border border-slate-200 text-[11px] font-semibold text-slate-700 hover:bg-blue-50 hover:text-blue-700"
                >
                  Operator
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* --- Scope Disclaimer Footer (HC-7) --- */}
      <footer className="bg-white border-t border-slate-200 py-6 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-start gap-2.5 text-[11px] text-slate-400 leading-relaxed text-justify bg-slate-50 p-3.5 rounded-lg border border-slate-100">
            <Info className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
            <span>
              <strong>STATUTORY SCOPE LIMITATION NOTICE (HC-7):</strong> {healthNotice}
            </span>
          </div>
        </div>
      </footer>
    </div>
  )
}
