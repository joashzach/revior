import { describe, expect, it } from 'vitest'
import { leadOf } from '@/lib/utils'

describe('leadOf', () => {
  it('keeps the sentence and drops the detail after a dash', () => {
    expect(leadOf("You're confirmed ✓ - MTC 570A Potheri → Guindy")).toBe("You're confirmed ✓")
    expect(leadOf('On time — 6:10 PM Chengalpattu')).toBe('On time')
  })
  it('leaves hyphenated words and plain headlines alone', () => {
    expect(leadOf('Placed on your 1st choice ✓')).toBe('Placed on your 1st choice ✓')
    expect(leadOf('Re-routed due to closure')).toBe('Re-routed due to closure')
  })
  it('strips a trailing full stop', () => {
    expect(leadOf('Request received.')).toBe('Request received')
  })
})
