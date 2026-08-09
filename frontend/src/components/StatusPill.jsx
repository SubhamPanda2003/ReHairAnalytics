/** Colored rounded label for a status/role value, driven by a `{ value: [label, classes] }` map. */
export default function StatusPill({ value, labels, fallbackClassName = "bg-muted" }) {
  const [label, className] = labels[value] || [value, fallbackClassName];
  return <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${className}`}>{label}</span>;
}
