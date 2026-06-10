import { useCallback, useRef, useState } from 'react'
import { fetchEnhancedStockDiagnosis, fetchStockDiagnosis } from '../api/stockApi'
import type { StockDiagnosis } from '../types/stock'
import type { StockItem } from '../types/theme'

const DIAGNOSIS_CACHE_TTL_MS = 24 * 60 * 60 * 1000

type DiagnosisDisplayMode = 'base' | 'enhanced'

type DiagnosisCacheEntry = {
  savedAt: number
  data: StockDiagnosis
}

const diagnosisCacheKey = (stock: Pick<StockItem, 'code' | 'name'>) => `${stock.code}|${stock.name}`

function readDiagnosisCache(cache: Map<string, DiagnosisCacheEntry>, key: string): StockDiagnosis | null {
  const entry = cache.get(key)
  if (!entry) return null
  if (Date.now() - entry.savedAt >= DIAGNOSIS_CACHE_TTL_MS) {
    cache.delete(key)
    return null
  }
  return entry.data
}

function writeDiagnosisCache(cache: Map<string, DiagnosisCacheEntry>, key: string, data: StockDiagnosis) {
  cache.set(key, { savedAt: Date.now(), data })
}

export function useStockDiagnosisController() {
  const [diagnosisStock, setDiagnosisStock] = useState<StockItem | null>(null)
  const [diagnosis, setDiagnosis] = useState<StockDiagnosis | null>(null)
  const [baseDiagnosis, setBaseDiagnosis] = useState<StockDiagnosis | null>(null)
  const [enhancedDiagnosis, setEnhancedDiagnosis] = useState<StockDiagnosis | null>(null)
  const [diagnosisLoading, setDiagnosisLoading] = useState(false)
  const [diagnosisEnhancing, setDiagnosisEnhancing] = useState(false)
  const [displayMode, setDisplayMode] = useState<DiagnosisDisplayMode>('base')
  const [diagnosisError, setDiagnosisError] = useState('')
  const diagnosisRequestId = useRef(0)
  const enhanceRequestId = useRef(0)
  const diagnosisCacheRef = useRef<Map<string, DiagnosisCacheEntry>>(new Map())
  const enhancedDiagnosisCacheRef = useRef<Map<string, DiagnosisCacheEntry>>(new Map())

  const selectStock = useCallback((stock: StockItem) => {
    const requestId = diagnosisRequestId.current + 1
    diagnosisRequestId.current = requestId
    enhanceRequestId.current += 1
    const cacheKey = diagnosisCacheKey(stock)
    const cachedBase = readDiagnosisCache(diagnosisCacheRef.current, cacheKey)
    const cachedEnhanced = readDiagnosisCache(enhancedDiagnosisCacheRef.current, cacheKey)
    setDiagnosisStock(stock)
    setDiagnosis(cachedBase)
    setBaseDiagnosis(cachedBase)
    setEnhancedDiagnosis(cachedEnhanced)
    setDiagnosisError('')
    setDiagnosisLoading(!cachedBase)
    setDiagnosisEnhancing(false)
    setDisplayMode('base')

    if (cachedBase) return

    fetchStockDiagnosis(stock.code, stock.name)
      .then((result) => {
        if (diagnosisRequestId.current !== requestId) return
        writeDiagnosisCache(diagnosisCacheRef.current, cacheKey, result)
        setDiagnosis(result)
        setBaseDiagnosis(result)
      })
      .catch((err) => {
        if (diagnosisRequestId.current !== requestId) return
        const message = err?.response?.data?.detail || err?.message || '个股诊断生成失败'
        setDiagnosisError(message)
      })
      .finally(() => {
        if (diagnosisRequestId.current !== requestId) return
        setDiagnosisLoading(false)
      })
  }, [])

  const closeDiagnosis = useCallback(() => {
    diagnosisRequestId.current += 1
    enhanceRequestId.current += 1
    setDiagnosisStock(null)
    setDiagnosis(null)
    setBaseDiagnosis(null)
    setEnhancedDiagnosis(null)
    setDiagnosisError('')
    setDiagnosisLoading(false)
    setDiagnosisEnhancing(false)
    setDisplayMode('base')
  }, [])

  const toggleEnhanced = useCallback(
    (stock: StockItem) => {
      if (displayMode === 'enhanced') {
        if (baseDiagnosis) setDiagnosis(baseDiagnosis)
        setDisplayMode('base')
        setDiagnosisEnhancing(false)
        return
      }
      if (enhancedDiagnosis) {
        setDiagnosis(enhancedDiagnosis)
        setDisplayMode('enhanced')
        setDiagnosisEnhancing(false)
        return
      }
      const cacheKey = diagnosisCacheKey(stock)
      const cachedEnhanced = readDiagnosisCache(enhancedDiagnosisCacheRef.current, cacheKey)
      if (cachedEnhanced) {
        setDiagnosis(cachedEnhanced)
        setEnhancedDiagnosis(cachedEnhanced)
        setDisplayMode('enhanced')
        setDiagnosisEnhancing(false)
        return
      }
      const requestId = enhanceRequestId.current + 1
      enhanceRequestId.current = requestId
      setBaseDiagnosis((current) => current || diagnosis)
      setDiagnosisEnhancing(true)

      fetchEnhancedStockDiagnosis(stock.code, stock.name)
        .then((result) => {
          if (enhanceRequestId.current !== requestId) return
          if (result.llm_status === 'ok') {
            writeDiagnosisCache(enhancedDiagnosisCacheRef.current, cacheKey, result)
          }
          setDiagnosis(result)
          setEnhancedDiagnosis(result)
          setDisplayMode('enhanced')
        })
        .catch(() => {
          if (enhanceRequestId.current !== requestId) return
          setDisplayMode('base')
          setDiagnosis((current) => (current ? { ...current, llm_status: 'error' } : current))
        })
        .finally(() => {
          if (enhanceRequestId.current !== requestId) return
          setDiagnosisEnhancing(false)
        })
    },
    [baseDiagnosis, diagnosis, displayMode, enhancedDiagnosis],
  )

  return {
    diagnosisStock,
    diagnosis,
    diagnosisLoading,
    diagnosisEnhancing,
    diagnosisEnhanced: displayMode === 'enhanced',
    diagnosisError,
    selectStock,
    closeDiagnosis,
    toggleEnhanced,
  }
}
