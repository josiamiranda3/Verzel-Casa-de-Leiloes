import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'

const API = (import.meta.env.VITE_API_URL || 'http://localhost:8001').replace(/\/+$/, '')
const TOKEN_KEY = 'verzel_access_token'
type AnyRecord = Record<string, unknown>

function money(value: unknown) {
  const amount = Number(value)
  return Number.isFinite(amount) ? amount.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) : '—'
}
function date(value: unknown) {
  const parsed = new Date(String(value))
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString('pt-BR')
}
async function api(path: string, init: RequestInit = {}) {
  const token = localStorage.getItem(TOKEN_KEY) || ''
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  })
  const data = await response.json().catch(() => ({}))
  if (response.status === 401 && token) {
    window.dispatchEvent(new CustomEvent('verzel:unauthorized'))
  }
  if (!response.ok) {
    const detail = (data as { detail?: unknown }).detail
    throw new Error(typeof detail === 'string' ? detail : `Falha HTTP ${response.status}`)
  }
  return data
}
function PageShell({ title, children }: { title: string; children: ReactNode }) {
  return <main className="portal-page">
    <header className="portal-header"><a href="/">← Voltar à vitrine</a><h1>{title}</h1></header>
    {children}
  </main>
}
export function WalletPage() {
  const [wallet, setWallet] = useState<AnyRecord | null>(null)
  const [transactions, setTransactions] = useState<AnyRecord[]>([])
  const [amount, setAmount] = useState('100')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [accessDenied, setAccessDenied] = useState(false)
  async function load() {
    try {
      const [w, t] = await Promise.all([api('/wallet/me'), api('/wallet/me/transactions')])
      setWallet(w as AnyRecord); setTransactions(Array.isArray(t) ? t as AnyRecord[] : [])
      setAccessDenied(false)
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Erro ao consultar carteira'
      const denied = message.toLowerCase().includes('somente para arrematantes')
      setAccessDenied(denied)
      setError(denied ? '' : message)
    }
  }
  // O carregamento inicial é intencional; load usa apenas setters estáveis.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void load() }, [])
  async function deposit(event: FormEvent) {
    event.preventDefault(); setError(''); setMessage('')
    try {
      await api('/wallet/deposit', { method: 'POST', body: JSON.stringify({ amount: Number(amount).toFixed(2) }) })
      setMessage('Depósito simulado registrado.'); await load()
    } catch (e) { setError(e instanceof Error ? e.message : 'Falha no depósito') }
  }
  return <PageShell title="Minha carteira">
    {error && <p className="portal-error">{error}</p>}{message && <p className="portal-success">{message}</p>}
    {accessDenied && <p className="portal-error">A carteira de depósitos e lances é exclusiva do arrematante. Entre com uma conta de arrematante para consultar saldo, movimentações e fazer depósitos simulados.</p>}
    {!accessDenied && wallet && <section className="portal-grid">
      <article className="portal-card"><span>Saldo total</span><strong>{money(wallet.balance)}</strong></article>
      <article className="portal-card"><span>Saldo comprometido</span><strong>{money(wallet.committed_balance)}</strong></article>
      <article className="portal-card"><span>Saldo disponível</span><strong>{money(wallet.available_balance)}</strong></article>
    </section>}
    {!accessDenied && <section className="portal-card"><h2>Depósito simulado</h2><form className="portal-form" onSubmit={deposit}>
      <label>Valor (R$)<input type="number" min="1" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} required /></label>
      <button type="submit">Adicionar saldo de teste</button>
    </form><small>Este saldo é fictício e serve exclusivamente para demonstração.</small></section>}
    {!accessDenied && <section className="portal-card"><h2>Movimentações</h2>{transactions.length === 0 ? <p>Nenhuma movimentação registrada.</p> :
      <div className="portal-table-wrap"><table className="portal-table"><thead><tr><th>Data</th><th>Tipo</th><th>Direção</th><th>Descrição</th><th>Valor</th><th>Lote</th></tr></thead><tbody>
        {transactions.map(t => <tr key={String(t.id)}><td>{date(t.created_at)}</td><td>{String(t.transaction_type)}</td><td>{String(t.direction || '—')}</td><td>{String(t.description || '—')}</td><td>{money(t.amount)}</td><td>{String(t.lot_id ?? '—')}</td></tr>)}
      </tbody></table></div>}
    </section>}
  </PageShell>
}
export function AuctioneerPage() {
  const [query, setQuery] = useState('')
  const [items, setItems] = useState<AnyRecord[]>([])
  const [lots, setLots] = useState<AnyRecord[]>([])
  const [totalReceived, setTotalReceived] = useState<unknown>(0)
  const [selected, setSelected] = useState<AnyRecord | null>(null)
  const [mode, setMode] = useState<'manual' | 'external'>('manual')
  const [review, setReview] = useState<AnyRecord | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [imageUrl, setImageUrl] = useState('')
  const [initialBid, setInitialBid] = useState('100')
  const [increment, setIncrement] = useState('10')
  const [starts, setStarts] = useState('')
  const [ends, setEnds] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function loadLots() {
    try {
      const data = await api('/lots/mine/managed') as { lots?: AnyRecord[]; total_received?: unknown }
      setLots(Array.isArray(data.lots) ? data.lots : [])
      setTotalReceived(data.total_received ?? 0)
    } catch (e) { setError(e instanceof Error ? e.message : 'Não foi possível carregar lotes') }
  }
  // Carrega os lotes do leiloeiro ao abrir o painel.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void loadLots() }, [])

  async function searchItems(e: FormEvent) {
    e.preventDefault(); setError(''); setMessage('')
    try {
      const data = await api(`/lots/external/search?q=${encodeURIComponent(query)}`)
      setItems((data as {items?: AnyRecord[]}).items || [])
    } catch (e) { setError(e instanceof Error ? e.message : 'Falha na busca externa') }
  }

  function prepareManualReview(e: FormEvent) {
    e.preventDefault(); setError(''); setMessage('')
    if (!title.trim() || title.trim().length < 3) { setError('Informe um título com pelo menos 3 caracteres.'); return }
    if (Number(initialBid) <= 0 || Number(increment) <= 0) { setError('O lance inicial e o incremento devem ser maiores que zero.'); return }
    const startDate = new Date(starts)
    const endDate = new Date(ends)
    if (!starts || !ends || Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime()) || endDate <= startDate) {
      setError('Informe datas válidas e um encerramento posterior ao início.'); return
    }
    setReview({
      title: title.trim(), description: description.trim(), image_url: imageUrl.trim() || null,
      initial_bid: Number(initialBid).toFixed(2), minimum_increment: Number(increment).toFixed(2),
      starts_at: startDate.toISOString(), ends_at: endDate.toISOString(),
    })
  }

  async function publishLot() {
    if (!review || saving) return
    setError(''); setMessage(''); setSaving(true)
    try {
      await api('/lots/', { method: 'POST', body: JSON.stringify(review) })
      setMessage('Lote cadastrado com sucesso. Ele já está disponível conforme o status e as datas definidos pela API.')
      setReview(null); setTitle(''); setDescription(''); setImageUrl('')
      setInitialBid('100'); setIncrement('10'); setStarts(''); setEnds('')
      await loadLots()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Falha ao cadastrar lote')
    } finally { setSaving(false) }
  }

  async function createExternalLot(e: FormEvent) {
    e.preventDefault(); if (!selected) return
    setError(''); setMessage('')
    try {
      const startDate = new Date(starts)
      const endDate = new Date(ends)
      if (!starts || !ends || endDate <= startDate) { setError('Informe datas válidas e um encerramento posterior ao início.'); return }
      setReview({
        title: String(selected.title || ''),
        description: `Item importado da Open Library. Autores: ${Array.isArray(selected.authors) ? selected.authors.join(', ') : 'não informado'}.`,
        image_url: selected.image_url || null, initial_bid: Number(initialBid).toFixed(2),
        minimum_increment: Number(increment).toFixed(2), starts_at: startDate.toISOString(), ends_at: endDate.toISOString()
      })
    } catch { setError('Não foi possível preparar a revisão do lote.') }
  }

  async function lotAction(id: unknown, action: 'cancel' | 'settle') {
    setError(''); setMessage('')
    try {
      const data = await api(`/lots/${id}/${action}`, { method: 'POST' })
      setMessage(action === 'cancel' ? 'Lote cancelado.' : `Liquidação concluída: ${JSON.stringify(data)}`)
      await loadLots()
    } catch (e) { setError(e instanceof Error ? e.message : 'Ação não concluída') }
  }

  return <PageShell title="Painel do leiloeiro">
    {error && <p className="portal-error" role="alert">{error}</p>}
    {message && <p className="portal-success" role="status">{message}</p>}

    <section className="portal-card">
      <h2>Cadastrar lote</h2>
      <p>Cadastre um item manualmente ou procure um livro na Open Library. Antes de salvar, você poderá revisar os dados.</p>
      <div className="portal-mode-switch" role="group" aria-label="Método de cadastro">
        <button type="button" className={mode === 'manual' ? 'selected' : 'secondary'} onClick={() => { setMode('manual'); setReview(null); setSelected(null); setError('') }}>Cadastro manual</button>
        <button type="button" className={mode === 'external' ? 'selected' : 'secondary'} onClick={() => { setMode('external'); setReview(null); setError('') }}>Buscar na Open Library</button>
      </div>

      {mode === 'manual' && !review && <form className="portal-form portal-lot-form" onSubmit={prepareManualReview}>
        <label>Título do item<input value={title} onChange={e => setTitle(e.target.value)} minLength={3} maxLength={200} required placeholder="Ex.: Notebook para leilão" /></label>
        <label>Descrição<textarea value={description} onChange={e => setDescription(e.target.value)} rows={4} placeholder="Descreva o item, suas condições e características." /></label>
        <label>URL da imagem<input type="url" value={imageUrl} onChange={e => setImageUrl(e.target.value)} placeholder="https://exemplo.com/imagem.jpg" /><small>Use um endereço HTTPS público. O backend atual aceita image_url; upload de arquivo exige configurar armazenamento persistente.</small></label>
        {imageUrl.trim() && <img className="portal-image-preview" src={imageUrl} alt="Prévia da imagem do lote" onError={e => { e.currentTarget.style.display = 'none' }} onLoad={e => { e.currentTarget.style.display = 'block' }} />}
        <label>Lance inicial (R$)<input type="number" min="0.01" step="0.01" value={initialBid} onChange={e => setInitialBid(e.target.value)} required /></label>
        <label>Incremento mínimo (R$)<input type="number" min="0.01" step="0.01" value={increment} onChange={e => setIncrement(e.target.value)} required /></label>
        <label>Data e hora de início<input type="datetime-local" value={starts} onChange={e => setStarts(e.target.value)} required /></label>
        <label>Data e hora de encerramento<input type="datetime-local" value={ends} onChange={e => setEnds(e.target.value)} required /></label>
        <button type="submit">Revisar lote</button>
      </form>}

      {mode === 'external' && <>
        <form className="portal-form" onSubmit={searchItems}>
          <label>Livro ou item<input value={query} onChange={e => setQuery(e.target.value)} minLength={2} required placeholder="Ex.: Dom Casmurro" /></label>
          <button type="submit">Buscar na Open Library</button>
        </form>
        <div className="portal-items">{items.map(item => <button type="button" className={`portal-item ${selected?.external_id === item.external_id ? 'selected' : ''}`} key={String(item.external_id)} onClick={() => { setSelected(item); setReview(null) }}>
          {typeof item.image_url === 'string' && item.image_url.length > 0 && <img src={item.image_url} alt="" />}
          <strong>{String(item.title)}</strong><span>{Array.isArray(item.authors) ? item.authors.join(', ') : ''}</span><small>{String(item.year || '')}</small>
        </button>)}</div>
        {selected && !review && <form className="portal-form portal-lot-form" onSubmit={createExternalLot}>
          <h3>Configurar lote: {String(selected.title)}</h3>
          <label>Lance inicial (R$)<input type="number" min="0.01" step="0.01" value={initialBid} onChange={e => setInitialBid(e.target.value)} required /></label>
          <label>Incremento mínimo (R$)<input type="number" min="0.01" step="0.01" value={increment} onChange={e => setIncrement(e.target.value)} required /></label>
          <label>Data e hora de início<input type="datetime-local" value={starts} onChange={e => setStarts(e.target.value)} required /></label>
          <label>Data e hora de encerramento<input type="datetime-local" value={ends} onChange={e => setEnds(e.target.value)} required /></label>
          <button type="submit">Revisar lote</button>
        </form>}
      </>}
    </section>

    {review && <section className="portal-card portal-review-card">
      <h2>Revisar informações antes de publicar</h2>
      <p>Confira os dados. Ao confirmar, o formulário enviará o lote para a API, que valida as regras e determina o status a partir das datas.</p>
      {typeof review.image_url === 'string' && <img className="portal-image-preview" src={review.image_url} alt={`Imagem de ${String(review.title)}`} />}
      <dl className="portal-review-list">
        <dt>Título</dt><dd>{String(review.title)}</dd>
        <dt>Descrição</dt><dd>{String(review.description || 'Sem descrição')}</dd>
        <dt>Lance inicial</dt><dd>{money(review.initial_bid)}</dd>
        <dt>Incremento mínimo</dt><dd>{money(review.minimum_increment)}</dd>
        <dt>Início</dt><dd>{date(review.starts_at)}</dd>
        <dt>Encerramento</dt><dd>{date(review.ends_at)}</dd>
      </dl>
      <div className="portal-review-actions">
        <button type="button" disabled={saving} onClick={() => void publishLot()}>{saving ? 'Publicando…' : 'Confirmar e cadastrar lote'}</button>
        <button type="button" className="secondary" disabled={saving} onClick={() => setReview(null)}>Voltar e editar</button>
      </div>
    </section>}

    <section className="portal-card"><h2>Meus lotes</h2><p>Total recebido em lotes liquidados: <strong>{money(totalReceived)}</strong></p>
      <div className="portal-table-wrap"><table className="portal-table"><thead><tr><th>Lote</th><th>Status</th><th>Início / fim</th><th>Resultado</th><th>Ações</th></tr></thead><tbody>
        {lots.map(l => <tr key={String(l.id)}><td>#{String(l.id)} — {String(l.title)}</td><td>{String(l.status)}</td><td>{date(l.starts_at)}<br/>{date(l.ends_at)}</td><td>{l.is_settled ? (l.winning_amount == null ? 'Encerrado sem lances' : `Arrematado por ${money(l.winning_amount)}`) : 'Ainda não liquidado'}</td><td className="portal-actions">
          {l.status !== 'closed' && l.status !== 'cancelled' && <button onClick={() => void lotAction(l.id,'cancel')}>Cancelar</button>}
          {l.status !== 'cancelled' && !l.is_settled && <button onClick={() => void lotAction(l.id,'settle')}>Liquidar</button>}
          {l.status === 'closed' && l.is_settled && <a href={`/lots/${String(l.id)}/receipt`}>Comprovante</a>}
        </td></tr>)}
      </tbody></table></div>
    </section>
  </PageShell>
}
export function MyWinsPage() {
  const [wins,setWins] = useState<AnyRecord[]>([])
  const [error,setError] = useState('')
  useEffect(() => { api('/lots/mine/wins').then(d => setWins(Array.isArray(d) ? d as AnyRecord[] : [])).catch(e => setError(e instanceof Error ? e.message : 'Falha ao consultar arremates')) }, [])
  return <PageShell title="Meus arremates">{error && <p className="portal-error">{error}</p>}
    {wins.length === 0 ? <section className="portal-card"><p>Nenhum arremate encontrado para esta conta.</p></section> : wins.map(w => <section className="portal-card" key={String(w.lot_id)}><h2>{String(w.title)}</h2><p>Arremate: <strong>{money(w.winning_amount)}</strong></p><p>Encerrado em {date(w.ends_at)}</p><a href={String(w.receipt_url)}>Abrir comprovante público</a></section>)}
  </PageShell>
}
export function ReceiptPage() {
  const id = window.location.pathname.match(/^\/lots\/(\d+)\/receipt\/?$/)?.[1]
  const [receipt,setReceipt] = useState<AnyRecord|null>(null)
  const [error,setError] = useState('')
  useEffect(() => { if (id) api(`/lots/${id}/receipt`).then(d => setReceipt(d as AnyRecord)).catch(e => setError(e instanceof Error ? e.message : 'Falha ao carregar comprovante')) }, [id])
  return <PageShell title="Comprovante público">{error && <p className="portal-error">{error}</p>}{receipt && <section className="portal-card receipt"><h2>{String(receipt.receipt_id)}</h2><p><strong>{String(receipt.lot_title)}</strong></p><p>Status: {String(receipt.status)}</p><p>Vencedor: {String(receipt.winner_reference || 'Sem vencedor')}</p><p>Valor: {money(receipt.winning_amount)}</p><p>{String(receipt.message)}</p><button onClick={() => void navigator.clipboard.writeText(window.location.href)}>Copiar link do comprovante</button></section>}</PageShell>
}
export function AuditPage() {
  const id = window.location.pathname.match(/^\/audit\/lots\/(\d+)\/?$/)?.[1]
  const [audit,setAudit] = useState<AnyRecord|null>(null)
  const [error,setError] = useState('')
  useEffect(() => { if (id) api(`/audit/lots/${id}`).then(d => setAudit(d as AnyRecord)).catch(e => setError(e instanceof Error ? e.message : 'Falha na auditoria')) }, [id])
  return <PageShell title="Auditoria pública">{error && <p className="portal-error">{error}</p>}{audit && <section className="portal-card"><pre>{JSON.stringify(audit,null,2)}</pre></section>}</PageShell>
}
