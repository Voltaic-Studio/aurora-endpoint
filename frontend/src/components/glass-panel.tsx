import { ComponentPropsWithoutRef, ElementType, ReactNode } from "react";

type GlassPanelProps<T extends ElementType = "div"> = {
  as?: T;
  children?: ReactNode;
  className?: string;
} & Omit<ComponentPropsWithoutRef<T>, "as" | "children" | "className">;

function joinClasses(...classes: Array<string | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export function GlassPanel<T extends ElementType = "div">({
  as,
  children,
  className,
  ...props
}: GlassPanelProps<T>) {
  const Component = as ?? "div";

  return (
    <Component
      className={joinClasses(
        "border border-white/18 bg-white/10 shadow-[0_24px_80px_rgba(0,0,0,0.34)] backdrop-blur-[24px]",
        className,
      )}
      {...props}
    >
      {children}
    </Component>
  );
}
