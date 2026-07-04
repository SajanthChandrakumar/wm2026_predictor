import * as SwitchPrimitive from '@radix-ui/react-switch'

export function Switch({ checked, onCheckedChange }: { checked: boolean; onCheckedChange: (v: boolean) => void }) {
  return (
    <SwitchPrimitive.Root
      checked={checked}
      onCheckedChange={onCheckedChange}
      className="relative h-5 w-9 shrink-0 cursor-pointer rounded-full border border-line-2 bg-surface-2 transition-colors data-[state=checked]:border-emerald-a/50 data-[state=checked]:bg-emerald-dim"
    >
      <SwitchPrimitive.Thumb className="block h-3.5 w-3.5 translate-x-0.5 rounded-full bg-fg-3 transition-transform data-[state=checked]:translate-x-[18px] data-[state=checked]:bg-emerald-a" />
    </SwitchPrimitive.Root>
  )
}
