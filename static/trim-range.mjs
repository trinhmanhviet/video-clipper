// Keep a positive selection even when handles cross or a clip is shorter than a frame.
export function clampTrimHandle(edge, value, other, duration, fps) {
  const gap = Math.min(duration, 1 / (fps || 30));
  const safe = Number.isFinite(value) ? value : edge === 'start' ? 0 : duration;
  return edge === 'start'
    ? Math.max(0, Math.min(safe, other - gap))
    : Math.min(duration, Math.max(safe, other + gap));
}
