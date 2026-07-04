import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '../../lib/util'

interface Props extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  hover?: boolean
}

export function GlassCard({ children, hover, className, ...rest }: Props) {
  return (
    <div className={cn('glass p-5', hover && 'glass-hover cursor-pointer', className)} {...rest}>
      {children}
    </div>
  )
}

export function SectionTitle({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <h2 className={cn('text-xs font-bold uppercase tracking-[0.15em] text-fg-3', className)}>
      {children}
    </h2>
  )
}
