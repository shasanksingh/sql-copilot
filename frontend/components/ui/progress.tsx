import { cn } from "@/lib/utils";

export function Progress({ value, className }: { value: number; className?: string }) {
  const boundedValue = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("h-2 overflow-hidden rounded-full bg-white/10 shadow-inner", className)}>
      <div className="h-full rounded-full bg-gradient-to-r from-cyan-300 via-sky-300 to-indigo-400 shadow-[0_0_16px_rgba(34,211,238,0.52)] transition-[width] duration-500" style={{ width: `${boundedValue}%` }} />
    </div>
  );
}