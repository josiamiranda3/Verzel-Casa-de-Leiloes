import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

type LotStatus = 'scheduled' | 'live' | 'closed' | 'cancelled'

type ApiLot = {
  id: number
  auctioneer_id: number
  title: string
  description: string | null
  image_url: string | null
  initial_bid: number | string
  minimum_increment: number | string
  starts_at: string
  ends_at: string
  status: LotStatus
}

type ApiBid = {
  id: number
  lot_id: number
  amount: number | string
  created_at: string
}

type LoginResponse = {
  access_token: string
  token_type: string
}

type AuctionLot = {
  id: number
  title: string
  description: string
  currentBid: number
  minimumIncrement: number
  endsAt: string
  startsAt: string
  image: string | null
  status: LotStatus
}

const API_URL = (
  import.meta.env.VITE_API_URL || 'http://localhost:8001'
).replace(/\/+$/, '')

const TOKEN_KEY = 'verzel_access_token'
const FAVORITES_KEY = 'verzel_favorite_lots'

const statusLabels: Record<LotStatus, string> = {
  scheduled: 'Em breve',
  live: 'Ao vivo',
  closed: 'Encerrado',
  cancelled: 'Cancelado',
}

const validStatuses: LotStatus[] = [
  'scheduled',
  'live',
  'closed',
  'cancelled',
]

const fallbackImage =
  'https://images.unsplash.com/photo-1577083552431-6e5fd01aa342?auto=format&fit=crop&w=900&q=85'

function formatPrice(price: number) {
  return price.toLocaleString('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function formatDate(value: string) {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return 'Data não disponível'
  }

  return date.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function getTimeRemaining(value: string) {
  const difference = new Date(value).getTime() - Date.now()

  if (!Number.isFinite(difference)) {
    return 'Data indisponível'
  }

  if (difference <= 0) {
    return 'Prazo atingido'
  }

  const totalMinutes = Math.floor(difference / 60000)
  const days = Math.floor(totalMinutes / 1440)
  const hours = Math.floor((totalMinutes % 1440) / 60)
  const minutes = totalMinutes % 60

  if (days > 0) return `${days}d ${hours}h restantes`
  if (hours > 0) return `${hours}h ${minutes}min restantes`

  return `${minutes}min restantes`
}

function mapApiLot(lot: ApiLot): AuctionLot {
  return {
    id: lot.id,
    title: lot.title,
    description: lot.description ?? '',
    currentBid: Number(lot.initial_bid),
    minimumIncrement: Number(lot.minimum_increment),
    startsAt: lot.starts_at,
    endsAt: lot.ends_at,
    image: lot.image_url,
    status: lot.status,
  }
}

// Calcula o status efetivo pelo relógio local, sem depender de a API
// já ter atualizado o campo status. Lotes cancelados/encerrados não reabrem.
function getEffectiveLotStatus(
  lot: Pick<AuctionLot, 'status' | 'startsAt' | 'endsAt'>,
  now = Date.now(),
): LotStatus {
  if (lot.status === 'cancelled' || lot.status === 'closed') {
    return lot.status
  }

  const startsAt = new Date(lot.startsAt).getTime()
  const endsAt = new Date(lot.endsAt).getTime()

  if (!Number.isFinite(startsAt) || !Number.isFinite(endsAt)) {
    return lot.status
  }

  if (now >= endsAt) return 'closed'
  if (now < startsAt) return 'scheduled'
  return 'live'
}

function getLotIdFromPath(): number | null {
  const match = window.location.pathname.match(/^\/?lots\/(\d+)\/?$/)

  if (!match) return null

  const id = Number(match[1])

  return Number.isSafeInteger(id) && id > 0 ? id : null
}

function isApiLot(value: unknown): value is ApiLot {
  if (typeof value !== 'object' || value === null) return false

  const lot = value as Partial<ApiLot>

  return (
    typeof lot.id === 'number' &&
    Number.isSafeInteger(lot.id) &&
    typeof lot.title === 'string' &&
    typeof lot.initial_bid !== 'undefined' &&
    Number.isFinite(Number(lot.initial_bid)) &&
    typeof lot.minimum_increment !== 'undefined' &&
    Number.isFinite(Number(lot.minimum_increment)) &&
    typeof lot.starts_at === 'string' &&
    typeof lot.ends_at === 'string' &&
    typeof lot.status === 'string' &&
    validStatuses.includes(lot.status as LotStatus)
  )
}

function isApiBid(value: unknown): value is ApiBid {
  if (typeof value !== 'object' || value === null) return false

  const bid = value as Partial<ApiBid>

  return (
    typeof bid.id === 'number' &&
    typeof bid.lot_id === 'number' &&
    typeof bid.amount !== 'undefined' &&
    Number.isFinite(Number(bid.amount)) &&
    typeof bid.created_at === 'string'
  )
}

function getApiError(data: unknown, fallback: string): string {
  if (
    typeof data === 'object' &&
    data !== null &&
    'detail' in data
  ) {
    const detail = (data as { detail?: unknown }).detail

    if (typeof detail === 'string') return detail

    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (
            typeof item === 'object' &&
            item !== null &&
            'msg' in item
          ) {
            return String(item.msg)
          }

          return String(item)
        })
        .join('; ')
    }
  }

  return fallback
}

function App() {
  const [lots, setLots] = useState<AuctionLot[]>([])
  const [catalogHighestBids, setCatalogHighestBids] = useState<Record<number, number>>({})
  const [search, setSearch] = useState('')
  const [activeStatus, setActiveStatus] =
    useState<'all' | LotStatus>('all')
  const [favorites, setFavorites] = useState<number[]>(() => {
    try {
      const saved = window.localStorage.getItem(FAVORITES_KEY)
      if (!saved) return []
      const parsed: unknown = JSON.parse(saved)
      return Array.isArray(parsed)
        ? parsed.filter(
            (id): id is number =>
              typeof id === 'number' && Number.isSafeInteger(id) && id > 0,
          )
        : []
    } catch {
      return []
    }
  })

  // Persiste os favoritos sempre que a lista for alterada.
  useEffect(() => {
    try {
      window.localStorage.setItem(
        FAVORITES_KEY,
        JSON.stringify(favorites),
      )
    } catch (error) {
      console.error('Não foi possível salvar os favoritos:', error)
    }
  }, [favorites])

  const [showFavoritesOnly, setShowFavoritesOnly] = useState(false)
  const [clock, setClock] = useState(() => Date.now())
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  const [selectedLotId, setSelectedLotId] = useState<number | null>(
    () => getLotIdFromPath(),
  )

  const [showLoginPage, setShowLoginPage] = useState(false)
  const [detailLot, setDetailLot] = useState<AuctionLot | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')

  const [lotBids, setLotBids] = useState<ApiBid[]>([])
  const [myPosition, setMyPosition] = useState<{has_bid: boolean; is_winning: boolean; own_highest_bid: number | string | null} | null>(null)
  const [bidsLoading, setBidsLoading] = useState(false)
  const [bidAmount, setBidAmount] = useState('')
  const [bidLoading, setBidLoading] = useState(false)
  const [bidError, setBidError] = useState('')
  const [bidSuccess, setBidSuccess] = useState('')

  const [loginEmail, setLoginEmail] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [loginLoading, setLoginLoading] = useState(false)
  const [loginError, setLoginError] = useState('')

  const [accessToken, setAccessToken] = useState(
    () => window.localStorage.getItem(TOKEN_KEY) ?? '',
  )
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [showAccountMenu, setShowAccountMenu] = useState(false)

  // Atualiza os estados calculados pelo horário sem exigir F5.
  useEffect(() => {
    const intervalId = window.setInterval(() => setClock(Date.now()), 1000)
    return () => window.clearInterval(intervalId)
  }, [])

  // Carrega o catálogo.
  useEffect(() => {
    const controller = new AbortController()

    async function fetchLots() {
      setIsLoading(true)
      setError('')

      try {
        const response = await fetch(`${API_URL}/lots/`, {
          signal: controller.signal,
          headers: { Accept: 'application/json' },
        })

        if (!response.ok) {
          throw new Error(
            `A API respondeu com o status HTTP ${response.status}.`,
          )
        }

        const data: unknown = await response.json()

        if (!Array.isArray(data)) {
          throw new Error('A API retornou um formato de dados inesperado.')
        }

        setLots(data.filter(isApiLot).map(mapApiLot))
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return

        setError(
          err instanceof Error
            ? err.message
            : 'Não foi possível carregar os lotes.',
        )
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      }
    }

    void fetchLots()

    return () => controller.abort()
  }, [])

  // Consulta os lances públicos para exibir o maior valor no catálogo.
  // A API de lotes retorna o lance inicial, não necessariamente o lance atual.
  useEffect(() => {
    if (lots.length === 0) {
      setCatalogHighestBids({})
      return
    }

    const controller = new AbortController()

    async function fetchCatalogBids() {
      const entries = await Promise.all(
        lots.map(async (lot): Promise<[number, number | null]> => {
          try {
            const response = await fetch(`${API_URL}/bids/lot/${lot.id}`, {
              signal: controller.signal,
              headers: { Accept: 'application/json' },
            })

            if (!response.ok) return [lot.id, null]

            const data: unknown = await response.json()
            if (!Array.isArray(data) || !data.every(isApiBid)) {
              return [lot.id, null]
            }

            if (data.length === 0) return [lot.id, null]

            const highest = data.reduce((current: ApiBid, bid: ApiBid) =>
              Number(bid.amount) > Number(current.amount) ? bid : current,
            )

            return [lot.id, Number(highest.amount)]
          } catch (err) {
            if (err instanceof Error && err.name === 'AbortError') {
              return [lot.id, null]
            }
            return [lot.id, null]
          }
        }),
      )

      if (controller.signal.aborted) return

      setCatalogHighestBids((current) => {
        const next = { ...current }
        for (const [lotId, amount] of entries) {
          if (amount === null) {
            delete next[lotId]
          } else {
            next[lotId] = amount
          }
        }
        return next
      })
    }

    void fetchCatalogBids()

    return () => controller.abort()
  }, [lots])

  // Carrega os detalhes do lote selecionado.
  useEffect(() => {
    if (selectedLotId === null) {
      return
    }

    const controller = new AbortController()

    async function fetchLotDetails() {
      setDetailLoading(true)
      setDetailError('')
      setDetailLot(null)

      try {
        const response = await fetch(`${API_URL}/lots/${selectedLotId}`, {
          signal: controller.signal,
          headers: { Accept: 'application/json' },
        })

        if (response.status === 404) {
          throw new Error('Este lote não foi encontrado.')
        }

        if (!response.ok) {
          throw new Error(
            `Não foi possível consultar o lote. HTTP ${response.status}.`,
          )
        }

        const data: unknown = await response.json()

        if (!isApiLot(data)) {
          throw new Error('A API retornou dados inválidos para este lote.')
        }

        if (data.id !== selectedLotId) {
          throw new Error('A API retornou um lote diferente do solicitado.')
        }

        setDetailLot(mapApiLot(data))
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return

        setDetailError(
          err instanceof Error
            ? err.message
            : 'Ocorreu um erro ao carregar os detalhes do lote.',
        )
      } finally {
        if (!controller.signal.aborted) {
          setDetailLoading(false)
        }
      }
    }

    void fetchLotDetails()

    return () => controller.abort()
  }, [selectedLotId])

  // Consulta os lances públicos do lote.
  useEffect(() => {
    if (selectedLotId === null) {
      return
    }

    const controller = new AbortController()

    async function fetchLotBids() {
      setBidsLoading(true)

      try {
        const response = await fetch(
          `${API_URL}/bids/lot/${selectedLotId}`,
          {
            signal: controller.signal,
            headers: { Accept: 'application/json' },
          },
        )

        if (!response.ok) {
          throw new Error('Não foi possível consultar os lances.')
        }

        const data: unknown = await response.json()

        if (!Array.isArray(data) || !data.every(isApiBid)) {
          throw new Error('A API retornou uma lista de lances inválida.')
        }

        setLotBids(data)
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return

        setBidError(
          err instanceof Error
            ? err.message
            : 'Não foi possível consultar os lances.',
        )
      } finally {
        if (!controller.signal.aborted) {
          setBidsLoading(false)
        }
      }
    }

    void fetchLotBids()

    return () => controller.abort()
  }, [selectedLotId])

  // Atualiza sala ao vivo periodicamente sem recarregar a página.
  useEffect(() => {
    if (selectedLotId === null) return
    const intervalId = window.setInterval(() => {
      void (async () => {
        try {
          const [bidsResponse, lotResponse] = await Promise.all([
            fetch(`${API_URL}/bids/lot/${selectedLotId}`, { headers: { Accept: 'application/json' } }),
            fetch(`${API_URL}/lots/${selectedLotId}`, { headers: { Accept: 'application/json' } }),
          ])
          if (bidsResponse.ok) {
            const bidsData: unknown = await bidsResponse.json()
            if (Array.isArray(bidsData) && bidsData.every(isApiBid)) setLotBids(bidsData)
          }
          if (lotResponse.ok) {
            const lotData: unknown = await lotResponse.json()
            if (isApiLot(lotData)) setDetailLot(mapApiLot(lotData))
          }
          if (accessToken) {
            const positionResponse = await fetch(`${API_URL}/bids/lot/${selectedLotId}/my-position`, {
              headers: { Accept: 'application/json', Authorization: `Bearer ${accessToken}` },
            })
            if (positionResponse.ok) setMyPosition(await positionResponse.json())
          } else {
            setMyPosition(null)
          }
        } catch {
          // A próxima tentativa automática atualizará a tela se a API voltar.
        }
      })()
    }, 5000)
    return () => window.clearInterval(intervalId)
  }, [selectedLotId, accessToken])

  // Sincroniza a tela com voltar e avançar do navegador.
  useEffect(() => {
    function handlePopState() {
      const lotId = getLotIdFromPath()
      setSelectedLotId(lotId)

      if (lotId === null) {
        setDetailLot(null)
        setDetailError('')
        setDetailLoading(false)
        setLotBids([])
        setBidError('')
        setBidSuccess('')
      }
    }

    window.addEventListener('popstate', handlePopState)

    return () => {
      window.removeEventListener('popstate', handlePopState)
    }
  }, [])

  const filteredLots = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase('pt-BR')

    return lots
      .map((lot) => ({ ...lot, status: getEffectiveLotStatus(lot, clock) }))
      .filter((lot) => {
      const matchesSearch =
        lot.title.toLocaleLowerCase('pt-BR').includes(normalizedSearch) ||
        lot.description.toLocaleLowerCase('pt-BR').includes(normalizedSearch)

      const matchesStatus =
        activeStatus === 'all' || lot.status === activeStatus

      const matchesFavorites = !showFavoritesOnly || favorites.includes(lot.id)

      return matchesSearch && matchesStatus && matchesFavorites
    })
  }, [lots, search, activeStatus, showFavoritesOnly, favorites, clock])

  const highestBid = useMemo(() => {
    if (lotBids.length === 0) return null

    return lotBids.reduce((highest, bid) =>
      Number(bid.amount) > Number(highest.amount) ? bid : highest,
    )
  }, [lotBids])

  const effectiveDetailStatus = detailLot
    ? getEffectiveLotStatus(detailLot, clock)
    : null

  const minimumAllowedBid = detailLot
    ? highestBid
      ? Number(highestBid.amount) + detailLot.minimumIncrement
      : detailLot.currentBid
    : 0

  function openLot(lotId: number) {
    window.history.pushState({}, '', `/lots/${lotId}`)
    setSelectedLotId(lotId)
    setBidAmount('')
    setBidError('')
    setBidSuccess('')
    window.scrollTo({ top: 0, behavior: 'auto' })
  }

  function goBackToCatalog(section?: string) {
    window.history.pushState({}, '', '/')
    setSelectedLotId(null)
    setDetailLot(null)
    setDetailError('')
    setDetailLoading(false)
    setLotBids([])
    setBidsLoading(false)
    setBidError('')
    setBidSuccess('')

    window.scrollTo({ top: 0, behavior: 'auto' })

    if (section) {
      window.setTimeout(() => {
        document.getElementById(section)?.scrollIntoView({
          behavior: 'smooth',
        })
      }, 0)
    }
  }

  // Abre uma seção pública mesmo quando a tela de login está substituindo o catálogo.
  function goToPublicSection(section: string) {
    setShowLoginPage(false)
    setLoginError('')
    setIsMobileMenuOpen(false)

    if (selectedLotId !== null) {
      goBackToCatalog(section)
      return
    }

    window.history.pushState({}, '', `/#${section}`)
    window.scrollTo({ top: 0, behavior: 'auto' })
    window.setTimeout(() => {
      document.getElementById(section)?.scrollIntoView({ behavior: 'smooth' })
    }, 0)
  }

  function toggleFavorite(lotId: number) {
    setFavorites((currentFavorites) =>
      currentFavorites.includes(lotId)
        ? currentFavorites.filter((id) => id !== lotId)
        : [...currentFavorites, lotId],
    )
  }

  function clearFilters() {
    setSearch('')
    setActiveStatus('all')
    setShowFavoritesOnly(false)
  }

  async function reloadLots() {
    setIsLoading(true)
    setError('')

    try {
      const response = await fetch(`${API_URL}/lots/`, {
        headers: { Accept: 'application/json' },
      })

      if (!response.ok) {
        throw new Error(`Falha ao consultar a API: HTTP ${response.status}.`)
      }

      const data: unknown = await response.json()

      if (!Array.isArray(data)) {
        throw new Error('A API retornou um formato de dados inesperado.')
      }

      setLots(data.filter(isApiLot).map(mapApiLot))
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Não foi possível atualizar os lotes.',
      )
    } finally {
      setIsLoading(false)
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLoginLoading(true)
    setLoginError('')
    setBidError('')
    setBidSuccess('')

    try {
      const response = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: loginEmail.trim(),
          password: loginPassword,
        }),
      })

      const data: unknown = await response.json()

      if (!response.ok) {
        throw new Error(getApiError(data, 'Não foi possível entrar.'))
      }

      if (
        typeof data !== 'object' ||
        data === null ||
        !('access_token' in data) ||
        typeof data.access_token !== 'string' ||
        data.access_token.length === 0
      ) {
        throw new Error('A API não retornou um token de acesso válido.')
      }

      const result = data as LoginResponse

      window.localStorage.setItem(TOKEN_KEY, result.access_token)
      setAccessToken(result.access_token)
      setLoginPassword('')
      setLoginError('')
      setShowLoginPage(false)
    } catch (err) {
      setLoginError(
        err instanceof Error ? err.message : 'Erro ao entrar.',
      )
    } finally {
      setLoginLoading(false)
    }
  }

    async function handleBid(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBidError('')
    setBidSuccess('')

    if (!detailLot) return

    if (getEffectiveLotStatus(detailLot) !== 'live') {
      setBidError('Este leilão não está aberto para lances neste momento.')
      return
    }

    if (!accessToken) {
      setBidError('Entre na sua conta de arrematante para ofertar um lance.')
      return
    }

    const normalizedAmount = bidAmount.trim().replace(',', '.')
    const amount = Number(normalizedAmount)

    if (
      normalizedAmount.length === 0 ||
      !Number.isFinite(amount) ||
      amount <= 0 ||
      !Number.isInteger(amount * 100)
    ) {
      setBidError('Informe um valor válido com até duas casas decimais.')
      return
    }

    if (amount < minimumAllowedBid) {
      setBidError(
        `O lance mínimo sugerido é ${formatPrice(minimumAllowedBid)}.`,
      )
      return
    }

    setBidLoading(true)

    try {
      const response = await fetch(`${API_URL}/bids/`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          lot_id: detailLot.id,
          amount: amount.toFixed(2),
        }),
      })

      const data: unknown = await response.json()

      if (!response.ok) {
        if (response.status === 401) {
          window.localStorage.removeItem(TOKEN_KEY)
          setAccessToken('')
          setLoginError('Sua sessão expirou. Entre novamente.')
        }

        throw new Error(
          getApiError(data, 'Não foi possível registrar o lance.'),
        )
      }

      setBidSuccess('Lance registrado com sucesso!')
      setBidAmount('')

      // Atualiza os lances a partir da resposta oficial da API.
      const bidsResponse = await fetch(
        `${API_URL}/bids/lot/${detailLot.id}`,
        { headers: { Accept: 'application/json' } },
      )

      if (bidsResponse.ok) {
        const bidsData: unknown = await bidsResponse.json()

        if (Array.isArray(bidsData) && bidsData.every(isApiBid)) {
          setLotBids(bidsData)
        }
      }

      // Atualiza também o estado do lote, caso tenha começado.
      const lotResponse = await fetch(`${API_URL}/lots/${detailLot.id}`, {
        headers: { Accept: 'application/json' },
      })

      if (lotResponse.ok) {
        const lotData: unknown = await lotResponse.json()

        if (isApiLot(lotData)) {
          setDetailLot(mapApiLot(lotData))
          setLots((current) =>
            current.map((lot) =>
              lot.id === lotData.id ? mapApiLot(lotData) : lot,
            ),
          )
        }
      }
    } catch (err) {
      setBidError(
        err instanceof Error
          ? err.message
          : 'Erro ao registrar o lance.',
      )
    } finally {
      setBidLoading(false)
    }
  }

  function logout() {
    window.localStorage.removeItem(TOKEN_KEY)
    setAccessToken('')
    setLoginPassword('')
    setLoginError('')
    setBidError('')
    setBidSuccess('')
    setShowLoginPage(false)
    setShowAccountMenu(false)
    setIsMobileMenuOpen(false)
    setMyPosition(null)
  }

  // Uniformiza o encerramento de sessão quando um portal recebe HTTP 401.
  useEffect(() => {
    const handleUnauthorized = () => logout()
    window.addEventListener('verzel:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('verzel:unauthorized', handleUnauthorized)
  }, [accessToken])

  // Se o JWT trouxer `exp`, encerra a sessão local quando ele expirar.
  useEffect(() => {
    if (!accessToken) return
    const checkExpiration = () => {
      try {
        const payloadPart = accessToken.split('.')[1]
        if (!payloadPart) return
        const normalized = payloadPart.replace(/-/g, '+').replace(/_/g, '/')
        const payload = JSON.parse(window.atob(normalized)) as { exp?: number }
        if (typeof payload.exp === 'number' && payload.exp * 1000 <= Date.now()) {
          logout()
        }
      } catch {
        // Tokens opacos ou payloads não decodificáveis continuam validados pela API.
      }
    }
    checkExpiration()
    const timer = window.setInterval(checkExpiration, 15000)
    return () => window.clearInterval(timer)
  }, [accessToken])

  return (
    <div className="app-shell">
      <div className="announcement">
        <span className="announcement-dot" aria-hidden="true" />
        <span>Sua próxima grande oportunidade começa aqui.</span>
        <a className="announcement-highlight" href="/#lotes">
          Descubra os leilões.
        </a>
      </div>

      <header className="site-header">
        <a
          className="brand"
          href="/"
          aria-label="Verzel — página inicial"
          onClick={(event) => {
            if (selectedLotId !== null) {
              event.preventDefault()
              goBackToCatalog()
            }
          }}
        >
          <span className="brand-symbol" aria-hidden="true">
            V
          </span>
          <span className="brand-name">
            VERZEL
            <small>CASA DE LEILÕES</small>
          </span>
        </a>

        <button
          className={`mobile-menu-toggle${isMobileMenuOpen ? ' is-open' : ''}`}
          type="button"
          aria-label={isMobileMenuOpen ? 'Fechar menu' : 'Abrir menu'}
          aria-expanded={isMobileMenuOpen}
          aria-controls="primary-navigation"
          onClick={() => setIsMobileMenuOpen((open) => !open)}
        >
          <span /><span /><span />
        </button>

        <nav
          id="primary-navigation"
          className={`main-nav${isMobileMenuOpen ? ' main-nav-open' : ''}`}
          aria-label="Navegação principal"
          onClick={(event) => {
            if ((event.target as HTMLElement).closest('a')) setIsMobileMenuOpen(false)
          }}
        >
          <a
            className={selectedLotId === null ? 'nav-active' : ''}
            href="/#inicio"
            onClick={(event) => {
              if (showLoginPage || selectedLotId !== null) {
                event.preventDefault()
                goToPublicSection('inicio')
              }
            }}
          >
            Início
          </a>

          <a
            href="/#lotes"
            onClick={(event) => {
              if (showLoginPage || selectedLotId !== null) {
                event.preventDefault()
                goToPublicSection('lotes')
              }
            }}
          >
            Explorar lotes
          </a>

          <a
            href="/#como-funciona"
            onClick={(event) => {
              if (showLoginPage || selectedLotId !== null) {
                event.preventDefault()
                goToPublicSection('como-funciona')
              }
            }}
          >
            Como funciona
          </a>

          <a href="/wallet">Carteira</a>
          <a href="/my-wins">Meus arremates</a>
          <a href="/auctioneer">Painel do leiloeiro</a>
          <a href="/audit/lots/1">Auditoria</a>
        </nav>

        <div className="header-actions">
          {accessToken ? (
            <div className="account-menu-wrap">
              <button
                className="account-status-button"
                type="button"
                aria-expanded={showAccountMenu}
                aria-haspopup="menu"
                onClick={() => setShowAccountMenu((open) => !open)}
              >
                <span className="account-status-dot" aria-hidden="true" />
                <span>Conta conectada</span>
                <span aria-hidden="true">⌄</span>
              </button>
              {showAccountMenu && (
                <div className="account-menu" role="menu">
                  <span className="account-menu-caption">SESSÃO ATIVA</span>
                  <a role="menuitem" href="/wallet" onClick={() => setShowAccountMenu(false)}>
                    Minha conta / carteira <span aria-hidden="true">↗</span>
                  </a>
                  <a role="menuitem" href="/auctioneer" onClick={() => setShowAccountMenu(false)}>
                    Painel do leiloeiro <span aria-hidden="true">↗</span>
                  </a>
                  <button role="menuitem" type="button" onClick={logout}>
                    Sair da conta
                  </button>
                </div>
              )}
            </div>
          ) : (
            <button
              className="login-link"
              type="button"
              onClick={() => {
                setShowLoginPage(true)
                setLoginError('')
                setShowAccountMenu(false)
                window.scrollTo({ top: 0, behavior: 'auto' })
              }}
            >
              Entrar
            </button>
          )}

          <a
            className="button button-primary header-cta"
            href="/#lotes"
            onClick={(event) => {
              if (showLoginPage || selectedLotId !== null) {
                event.preventDefault()
                goToPublicSection('lotes')
              }
            }}
          >
            Explorar leilões <span aria-hidden="true">↗</span>
          </a>
        </div>
      </header>

      <main
        className={
          showLoginPage
            ? 'login-page-mode'
            : selectedLotId !== null
              ? 'detail-mode'
              : ''
        }
      >
        {showLoginPage ? (
          <section className="standalone-login-section">
            <div className="standalone-login-card">
              <span className="standalone-login-eyebrow">
                VERZEL · CASA DE LEILÕES
              </span>

              <h1>Bem-vindo de volta.</h1>

              <p className="standalone-login-description">
                Entre na sua conta para participar dos leilões.
              </p>

              <form
                className="standalone-login-form"
                onSubmit={handleLogin}
              >
                <label htmlFor="standalone-login-email">E-mail</label>
                <input
                  id="standalone-login-email"
                  type="email"
                  autoComplete="email"
                  required
                  value={loginEmail}
                  onChange={(event) => setLoginEmail(event.target.value)}
                  placeholder="voce@exemplo.com"
                />

                <label htmlFor="standalone-login-password">Senha</label>
                <input
                  id="standalone-login-password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={loginPassword}
                  onChange={(event) => setLoginPassword(event.target.value)}
                  placeholder="Digite sua senha"
                />

                {loginError && (
                  <p className="bid-error" role="alert">
                    {loginError}
                  </p>
                )}

                <button
                  className="button button-primary standalone-login-submit"
                  type="submit"
                  disabled={loginLoading}
                >
                  {loginLoading
                    ? 'Entrando...'
                    : 'Entrar na minha conta'}
                </button>
              </form>

              <button
                className="standalone-login-back"
                type="button"
                onClick={() => {
                  setShowLoginPage(false)
                  setLoginError('')
                  window.history.pushState({}, '', '/')
                  window.scrollTo({ top: 0, behavior: 'auto' })
                }}
              >
                ← Voltar ao site
              </button>
            </div>
          </section>
        ) : selectedLotId === null ? (
          <>
            <section className="hero-section" id="inicio">
              <div className="hero-copy">
                <div className="eyebrow">
                  <span className="eyebrow-line" aria-hidden="true" />
                  UMA NOVA EXPERIÊNCIA EM LEILÕES
                </div>

                <h1>
                  Encontre algo
                  <br />
                  <span>extraordinário.</span>
                </h1>

                <p className="hero-description">
                  Descubra peças especiais, oportunidades únicas e novos
                  achados. Seu próximo grande negócio pode começar com um lance.
                </p>

                <div className="hero-actions">
                  <a className="button button-gold" href="#lotes">
                    Explorar oportunidades{' '}
                    <span aria-hidden="true">→</span>
                  </a>
                  <a className="text-link" href="#como-funciona">
                    Como funciona <span aria-hidden="true">↗</span>
                  </a>
                </div>

                <div className="hero-proof">
                  <div className="proof-item">
                    <strong>Oportunidades reais</strong>
                    <span>Consulte os lotes disponíveis</span>
                  </div>
                  <span className="proof-divider" aria-hidden="true" />
                  <div className="proof-item">
                    <strong>Dados atualizados</strong>
                    <span>Informações da plataforma</span>
                  </div>
                </div>
              </div>

              <div className="hero-visual">
                <img
                  className="hero-image"
                  src={fallbackImage}
                  alt="Obra de arte em uma galeria"
                />
                <div className="hero-image-shade" aria-hidden="true" />
                <div className="hero-image-label">
                  <span className="label-overline">
                    UM UNIVERSO DE POSSIBILIDADES
                  </span>
                  <strong>
                    Peças com história.
                    <br />
                    Novos destinos.
                  </strong>
                </div>
                <div className="floating-note">
                  <span className="floating-note-icon" aria-hidden="true">
                    ✳
                  </span>
                  <span>
                    <strong>Descubra o inesperado</strong>
                    <small>Explore os lotes disponíveis</small>
                  </span>
                </div>
                <span className="hero-index">01 — VERZEL COLLECTION</span>
              </div>
            </section>

            <section
              className="trust-strip"
              aria-label="Características da plataforma"
            >
              <div className="trust-item">
                <span className="trust-icon" aria-hidden="true">
                  ◇
                </span>
                <span>
                  <strong>Oportunidades especiais</strong>
                  <small>Descobertas selecionadas</small>
                </span>
              </div>
              <div className="trust-item">
                <span className="trust-icon" aria-hidden="true">
                  ◎
                </span>
                <span>
                  <strong>Experiência transparente</strong>
                  <small>Informações sobre os lotes</small>
                </span>
              </div>
              <div className="trust-item">
                <span className="trust-icon" aria-hidden="true">
                  ↗
                </span>
                <span>
                  <strong>Lances online</strong>
                  <small>Participe de onde estiver</small>
                </span>
              </div>
            </section>


            <section className="lots-section" id="lotes">
              <div className="section-heading">
                <div>
                  <div className="eyebrow">
                    <span className="eyebrow-line" aria-hidden="true" />
                    DESCUBRA SUA PRÓXIMA AQUISIÇÃO
                  </div>
                  <h2>
                    Oportunidades em <span>destaque.</span>
                  </h2>
                  <p>
                    Consulte os lotes cadastrados e acompanhe o status de cada
                    oportunidade.
                  </p>
                </div>
                <span className="lot-count" aria-live="polite">
                  {isLoading
                    ? 'Carregando...'
                    : `${filteredLots.length} ${filteredLots.length === 1 ? 'lote' : 'lotes'}`}
                </span>
              </div>

              <label className="search-box">
                <span aria-hidden="true">⌕</span>
                <input
                  type="search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Busque por título ou descrição..."
                  aria-label="Buscar lotes por título ou descrição"
                />
                <span className="search-shortcut" aria-hidden="true">
                  BUSCAR
                </span>
              </label>

              <div className="category-list" aria-label="Filtrar por status">
                {(
                  [
                    ['all', 'Todos'],
                    ['live', 'Ao vivo'],
                    ['scheduled', 'Em breve'],
                    ['closed', 'Encerrados'],
                    ['cancelled', 'Cancelados'],
                  ] as const
                ).map(([status, label]) => (
                  <button
                    key={status}
                    type="button"
                    className={`category-chip ${activeStatus === status ? 'selected' : ''}`}
                    onClick={() => setActiveStatus(status)}
                    aria-pressed={activeStatus === status}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <div className="category-list favorites-filter">
                <button
                  className={`category-chip ${showFavoritesOnly ? 'selected' : ''}`}
                  type="button"
                  onClick={() => setShowFavoritesOnly((current) => !current)}
                  aria-pressed={showFavoritesOnly}
                >
                  {showFavoritesOnly ? '♥ Exibindo favoritos' : `♡ Meus favoritos (${favorites.length})`}
                </button>
              </div>

              {error && (
                <div className="empty-state" role="alert">
                  <h3>Não foi possível carregar os lotes</h3>
                  <p>{error}</p>
                  <p>
                    Verifique se a API está funcionando em {API_URL} e tente
                    novamente.
                  </p>
                  <button
                    className="button button-primary"
                    type="button"
                    onClick={() => void reloadLots()}
                  >
                    Tentar novamente
                  </button>
                </div>
              )}

              {!error && isLoading && (
                <div
                  className="empty-state"
                  role="status"
                  aria-live="polite"
                >
                  <h3>Carregando oportunidades...</h3>
                  <p>
                    Estamos consultando os lotes cadastrados na plataforma.
                  </p>
                </div>
              )}

              {!error && !isLoading && filteredLots.length > 0 && (
                <div className="lot-grid">
                  {filteredLots.map((lot) => {
                    const isFavorite = favorites.includes(lot.id)

                    return (
                      <article className="lot-card" key={lot.id}>
                        <div className="lot-image-wrap">
                          <img
                            className="lot-image"
                            src={lot.image || fallbackImage}
                            alt={lot.title}
                            loading="lazy"
                            onError={(event) => {
                              event.currentTarget.onerror = null
                              event.currentTarget.src = fallbackImage
                            }}
                          />
                          <span
                            className={`lot-status ${lot.status === 'live' ? 'status-live' : 'status-upcoming'}`}
                          >
                            {lot.status === 'live' && (
                              <span
                                className="live-dot"
                                aria-hidden="true"
                              />
                            )}
                            {statusLabels[lot.status]}
                          </span>
                          <button
                            className="favorite-button"
                            type="button"
                            aria-label={
                              isFavorite
                                ? `Remover ${lot.title} dos favoritos`
                                : `Adicionar ${lot.title} aos favoritos`
                            }
                            aria-pressed={isFavorite}
                            onClick={() => toggleFavorite(lot.id)}
                          >
                            {isFavorite ? '♥' : '♡'}
                          </button>
                        </div>

                        <div className="lot-content">
                          <span className="lot-category">
                            Lote #{lot.id}
                          </span>
                          <h3>{lot.title}</h3>

                          {lot.description && (
                            <p className="lot-description">
                              {lot.description}
                            </p>
                          )}

                          <div className="lot-meta">
                            <span>
                              {lot.status === 'scheduled'
                                ? `Início: ${formatDate(lot.startsAt)}`
                                : lot.status === 'live'
                                  ? `Encerra: ${getTimeRemaining(lot.endsAt)}`
                                  : `Encerramento: ${formatDate(lot.endsAt)}`}
                            </span>
                          </div>

                          <div className="lot-footer">
                            <div>
                              <span className="price-label">
                                {catalogHighestBids[lot.id] !== undefined
                                  ? 'Maior lance atual'
                                  : 'Lance inicial'}
                              </span>
                              <strong className="lot-price">
                                {formatPrice(
                                  catalogHighestBids[lot.id] ?? lot.currentBid,
                                )}
                              </strong>
                            </div>
                            <button
                              className="lot-bid-button"
                              type="button"
                              onClick={() => openLot(lot.id)}
                              aria-label={`Ver detalhes de ${lot.title}`}
                            >
                              Ver lote <span aria-hidden="true">↗</span>
                            </button>
                          </div>

                          <p className="demo-notice">
                            Incremento mínimo:{' '}
                            {formatPrice(lot.minimumIncrement)}
                          </p>
                        </div>
                      </article>
                    )
                  })}
                </div>
              )}

              {!error && !isLoading && filteredLots.length === 0 && (
                <div className="empty-state">
                  <span aria-hidden="true">⌕</span>
                  <h3>
                    {lots.length === 0
                      ? 'Nenhum lote cadastrado'
                      : showFavoritesOnly && favorites.length === 0
                        ? 'Você ainda não favoritou nenhum lote'
                        : 'Nenhum lote encontrado'}
                  </h3>
                  <p>
                    {lots.length === 0
                      ? 'Os lotes aparecerão aqui quando forem cadastrados na plataforma.'
                      : showFavoritesOnly && favorites.length === 0
                        ? 'Use o coração nos cartões dos lotes para salvá-los aqui.'
                        : 'Tente outro termo de busca, desative o filtro de favoritos ou selecione outro status.'}
                  </p>
                  {lots.length > 0 ? (
                    <button
                      className="button button-primary"
                      type="button"
                      onClick={clearFilters}
                    >
                      Limpar filtros
                    </button>
                  ) : (
                    <button
                      className="button button-primary"
                      type="button"
                      onClick={() => void reloadLots()}
                    >
                      Atualizar catálogo
                    </button>
                  )}
                </div>
              )}
            </section>

            <section className="how-section" id="como-funciona">
              <div className="how-intro">
                <div className="eyebrow">
                  <span className="eyebrow-line" aria-hidden="true" />
                  SIMPLES E TRANSPARENTE
                </div>
                <h2>
                  Seu próximo lance começa <span>aqui.</span>
                </h2>
                <p>
                  Explore os lotes, confira as informações e conheça as regras
                  antes de participar.
                </p>
              </div>

              <div className="steps-grid">
                <article className="step-card">
                  <span className="step-number">01</span>
                  <h3>Explore os lotes</h3>
                  <p>
                    Encontre itens de seu interesse e conheça as informações
                    disponíveis.
                  </p>
                </article>
                <article className="step-card">
                  <span className="step-number">02</span>
                  <h3>Acompanhe as oportunidades</h3>
                  <p>
                    Confira o status, os valores e as datas antes de decidir
                    participar.
                  </p>
                </article>
                <article className="step-card">
                  <span className="step-number">03</span>
                  <h3>Prepare seu lance</h3>
                  <p>
                    Entre na sua conta, confira o valor mínimo e envie sua
                    oferta enquanto o leilão estiver aberto.
                  </p>
                </article>
              </div>
            </section>
          </>
        ) : (
          <section className="lot-detail-section">
            <button
              className="detail-back-button"
              type="button"
              onClick={() => goBackToCatalog('lotes')}
            >
              <span aria-hidden="true">←</span> Voltar ao catálogo
            </button>

            {detailLoading && (
              <div className="empty-state" role="status">
                <h3>Carregando detalhes do lote...</h3>
                <p>Estamos consultando as informações na plataforma.</p>
              </div>
            )}

            {!detailLoading && detailError && (
              <div className="empty-state" role="alert">
                <h3>Não foi possível abrir este lote</h3>
                <p>{detailError}</p>
                <button
                  className="button button-primary"
                  type="button"
                  onClick={() => goBackToCatalog('lotes')}
                >
                  Voltar ao catálogo
                </button>
              </div>
            )}

            {!detailLoading && !detailError && detailLot && (
              <article className="lot-detail-card">
                <div className="detail-image-wrap">
                  <img
                    src={detailLot.image || fallbackImage}
                    alt={detailLot.title}
                    onError={(event) => {
                      event.currentTarget.onerror = null
                      event.currentTarget.src = fallbackImage
                    }}
                  />
                  <span
                    className={`lot-status ${effectiveDetailStatus === 'live' ? 'status-live' : 'status-upcoming'}`}
                  >
                    {effectiveDetailStatus === 'live' && (
                      <span className="live-dot" aria-hidden="true" />
                    )}
                    {statusLabels[effectiveDetailStatus ?? detailLot.status]}
                  </span>
                </div>

                <div className="detail-content">
                  <span className="lot-category">
                    VERZEL COLLECTION · LOTE #{detailLot.id}
                  </span>

                  <h1>{detailLot.title}</h1>

                  <p className="detail-description">
                    {detailLot.description ||
                      'Nenhuma descrição foi disponibilizada para este lote.'}
                  </p>

                  <div className="detail-price-panel">
                    <span className="price-label">
                      {highestBid ? 'Maior lance atual' : 'Lance inicial'}
                    </span>
                    <strong className="detail-price">
                      {formatPrice(
                        highestBid
                          ? Number(highestBid.amount)
                          : detailLot.currentBid,
                      )}
                    </strong>
                    <span>
                      Incremento mínimo:{' '}
                      {formatPrice(detailLot.minimumIncrement)}
                    </span>
                    {bidsLoading && (
                      <span aria-live="polite">
                        Atualizando lances...
                      </span>
                    )}
                  </div>

                  <div className="detail-information">
                    <div>
                      <span>Início do leilão</span>
                      <strong>{formatDate(detailLot.startsAt)}</strong>
                    </div>
                    <div>
                      <span>Encerramento</span>
                      <strong>{formatDate(detailLot.endsAt)}</strong>
                    </div>
                    {effectiveDetailStatus === 'live' && (
                      <div>
                        <span>Tempo restante</span>
                        <strong>{getTimeRemaining(detailLot.endsAt)}</strong>
                      </div>
                    )}
                  </div>

                  <div className="bid-section">
                    <h2>Participar do leilão</h2>

                    {effectiveDetailStatus !== 'live' && (
                      <p className="detail-notice">
                        {effectiveDetailStatus === 'scheduled'
                          ? 'Este leilão ainda não começou.'
                          : effectiveDetailStatus === 'closed'
                            ? 'Este leilão está encerrado.'
                            : 'Este lote foi cancelado.'}
                      </p>
                    )}

                    {!accessToken ? (
                      <form
                        className="bid-login-form"
                        onSubmit={handleLogin}
                      >
                        <p>
                          Entre com sua conta de arrematante para ofertar um
                          lance.
                        </p>

                        <label htmlFor="login-email">E-mail</label>
                        <input
                          id="login-email"
                          type="email"
                          autoComplete="email"
                          required
                          value={loginEmail}
                          onChange={(event) =>
                            setLoginEmail(event.target.value)
                          }
                        />

                        <label htmlFor="login-password">Senha</label>
                        <input
                          id="login-password"
                          type="password"
                          autoComplete="current-password"
                          required
                          value={loginPassword}
                          onChange={(event) =>
                            setLoginPassword(event.target.value)
                          }
                        />

                        {loginError && (
                          <p className="bid-error" role="alert">
                            {loginError}
                          </p>
                        )}

                        {bidError && (
                          <p className="bid-error" role="alert">
                            {bidError}
                          </p>
                        )}

                        <button
                          className="button button-primary"
                          type="submit"
                          disabled={loginLoading}
                        >
                          {loginLoading
                            ? 'Entrando...'
                            : 'Entrar para dar um lance'}
                        </button>
                      </form>
                    ) : (
                      <form className="bid-login-form" onSubmit={handleBid}>
                        <label htmlFor="bid-amount">Seu lance (R$)</label>
                        <input
                          id="bid-amount"
                          type="number"
                          min="0.01"
                          step="0.01"
                          required
                          value={bidAmount}
                          onChange={(event) =>
                            setBidAmount(event.target.value)
                          }
                          placeholder="Informe o valor"
                        />

                        <p>
                          Lance mínimo sugerido:{' '}
                          <strong>{formatPrice(minimumAllowedBid)}</strong>
                        </p>

                        <p>
                          O valor será validado novamente pelo servidor antes
                          de ser aceito.
                        </p>

                        {bidError && (
                          <p className="bid-error" role="alert">
                            {bidError}
                          </p>
                        )}

                        {bidSuccess && (
                          <p className="bid-success" role="status">
                            {bidSuccess}
                          </p>
                        )}

                        <button
                          className="button button-primary"
                          type="submit"
                          disabled={
                            bidLoading ||
                            effectiveDetailStatus !== 'live' ||
                            bidsLoading
                          }
                        >
                          {bidLoading
                            ? 'Enviando lance...'
                            : 'Confirmar lance'}
                        </button>

                        <button
                          className="bid-logout"
                          type="button"
                          onClick={logout}
                        >
                          Sair da conta
                        </button>
                      </form>
                    )}
                  </div>

                  {bidError && accessToken && (
                    <p className="bid-error" role="alert">
                      {bidError}
                    </p>
                  )}

                  {accessToken && myPosition?.has_bid && (
                    <p className={myPosition.is_winning ? 'bid-success' : 'bid-error'} role="status">
                      {myPosition.is_winning ? 'Você está ganhando este leilão.' : 'Seu lance foi superado.'}
                    </p>
                  )}

                  {lotBids.length > 0 && (
                    <section className="bid-history">
                      <h2>Histórico de lances</h2>
                      <ul>
                        {lotBids.slice(0, 5).map((bid) => (
                          <li key={bid.id}>
                            <span>{formatDate(bid.created_at)}</span>
                            <strong>
                              {formatPrice(Number(bid.amount))}
                            </strong>
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}

                  <button
                    className="button button-primary detail-catalog-button"
                    type="button"
                    onClick={() => goBackToCatalog('lotes')}
                  >
                    Explorar outros lotes{' '}
                    <span aria-hidden="true">→</span>
                  </button>
                </div>
              </article>
            )}
          </section>
        )}
      </main>

      <footer className="site-footer" id="entrar">
        <a
          className="brand footer-brand"
          href="/"
          onClick={(event) => {
            if (selectedLotId !== null) {
              event.preventDefault()
              goBackToCatalog()
            }
          }}
        >
          <span className="brand-symbol" aria-hidden="true">
            V
          </span>
          <span className="brand-name">
            VERZEL
            <small>CASA DE LEILÕES</small>
          </span>
        </a>

        <p>Descubra oportunidades. Encontre algo extraordinário.</p>

        <span className="footer-copy">
          © {new Date().getFullYear()} Verzel. Projeto em desenvolvimento.
        </span>
      </footer>
    </div>
  )
}

export default App