import * as SliderPrimitive from '@radix-ui/react-slider'

interface Props {
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  accent?: string
}

export function Slider({ value, min, max, step, onChange, accent = 'var(--emerald)' }: Props) {
  return (
    <SliderPrimitive.Root
      className="relative flex h-5 w-full cursor-pointer touch-none select-none items-center"
      value={[value]}
      min={min}
      max={max}
      step={step}
      onValueChange={([v]) => onChange(v)}
    >
      <SliderPrimitive.Track className="relative h-1.5 grow rounded-full bg-surface-2">
        <SliderPrimitive.Range className="absolute h-full rounded-full" style={{ background: accent }} />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb
        className="block h-4 w-4 rounded-full border-2 bg-bg shadow focus:outline-none"
        style={{ borderColor: accent }}
      />
    </SliderPrimitive.Root>
  )
}
