import { cn } from "@/lib/utils";

export function Button({
  className,
  variant = "primary",
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "tertiary";
}) {
  const variantClass =
    variant === "primary"
      ? "btn-primary"
      : variant === "tertiary"
        ? "btn-tertiary"
        : "btn-secondary";
  return (
    <button className={cn(variantClass, className)} {...props}>
      {children}
    </button>
  );
}

export function Input({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input className={cn("input-marketplace", className)} {...props} />
  );
}

export function Select({
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn("input-marketplace appearance-none", className)}
      {...props}
    >
      {children}
    </select>
  );
}

export function Badge({
  className,
  variant = "default",
  children,
}: {
  className?: string;
  variant?: "default" | "secondary" | "outline";
  children: React.ReactNode;
}) {
  const variants = {
    default: "bg-muted text-foreground border-border",
    secondary: "bg-muted text-muted-foreground border-border",
    outline: "bg-card text-foreground border-border",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold",
        variants[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Chip({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-border bg-muted px-2.5 py-0.5 text-xs font-semibold text-muted-foreground",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Card({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "surface-elevated overflow-hidden transition-shadow duration-hover",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "border-b border-border px-[var(--space-20)] py-[var(--space-16)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function CardContent({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("p-[var(--space-20)]", className)}>{children}</div>
  );
}

export function Tile({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius-xl)] border border-border bg-card p-4 shadow-sm transition-shadow hover:shadow-hover",
        className,
      )}
    >
      {children}
    </div>
  );
}
