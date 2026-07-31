import { readdirSync, readFileSync, statSync } from 'node:fs'
import { resolve } from 'node:path'
import { test } from 'vitest'
import assert from 'node:assert/strict'

const rootDir = resolve(__dirname, '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

function collectSourceFiles(relativeDir: string): string[] {
  const absoluteDir = resolve(rootDir, relativeDir)
  const files: string[] = []

  for (const entry of readdirSync(absoluteDir)) {
    const absolutePath = resolve(absoluteDir, entry)
    const relativePath = absolutePath.slice(rootDir.length + 1)
    const stat = statSync(absolutePath)

    if (stat.isDirectory()) {
      files.push(...collectSourceFiles(relativePath))
      continue
    }

    if (/\.(html|css|less|scss|ts|vue)$/.test(entry)) {
      files.push(relativePath)
    }
  }

  return files
}

test('frontend runtime shell does not load public CDN or Google font resources', () => {
  const indexSource = readSource('index.html')

  assert.equal(indexSource.includes('fonts.googleapis.com'), false)
  assert.equal(indexSource.includes('fonts.gstatic.com'), false)
  assert.equal(indexSource.includes('cdn.jsdelivr.net'), false)
  assert.equal(indexSource.includes('unpkg.com'), false)
  assert.equal(/<link[^>]+https?:\/\//i.test(indexSource), false)
})

test('frontend source styles do not import mandatory public runtime resources', () => {
  const offenders = collectSourceFiles('src')
    .map((file) => [file, readSource(file)] as const)
    .filter(([, source]) => /@import\s+url\(["']?https?:\/\//i.test(source))
    .map(([file]) => file)

  assert.deepEqual(offenders, [])
})
