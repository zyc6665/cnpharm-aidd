export function replaceRecord<T>(target: Record<string, T>, next: Record<string, T>) {
  for (const key of Object.keys(target)) {
    delete target[key]
  }

  for (const [key, value] of Object.entries(next)) {
    target[key] = value as T
  }
}
