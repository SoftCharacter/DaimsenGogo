/**
 * 格式化价格（保留2位小数）
 */
export function formatPrice(price: number): string {
  return price.toFixed(2)
}

/**
 * 格式化涨跌幅（带正负号和百分比符号）
 */
export function formatChangePercent(percent: number): string {
  const sign = percent >= 0 ? '+' : ''
  return `${sign}${percent.toFixed(2)}%`
}

/**
 * 格式化成交额（自动转换为万/亿单位）
 */
export function formatVolume(volume: number): string {
  // 万亿级别
  if (volume >= 1_0000_0000_0000) {
    return `${(volume / 1_0000_0000_0000).toFixed(2)}万亿`
  }
  // 亿级别
  if (volume >= 1_0000_0000) {
    return `${(volume / 1_0000_0000).toFixed(0)}亿`
  }
  // 万级别
  if (volume >= 1_0000) {
    return `${(volume / 1_0000).toFixed(0)}万`
  }
  return volume.toFixed(0)
}
