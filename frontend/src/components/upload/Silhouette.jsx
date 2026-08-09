export default function Silhouette() {
  return (
    <svg viewBox="0 0 200 200" className="absolute inset-0 w-full h-full opacity-50 pointer-events-none" aria-hidden="true">
      <ellipse cx="100" cy="95" rx="55" ry="70" fill="none" stroke="white" strokeWidth="2" strokeDasharray="6 6" />
      <line x1="45" y1="85" x2="155" y2="85" stroke="white" strokeWidth="1.5" strokeDasharray="4 4" />
      <circle cx="80" cy="85" r="4" fill="none" stroke="white" strokeWidth="1.5" />
      <circle cx="120" cy="85" r="4" fill="none" stroke="white" strokeWidth="1.5" />
    </svg>
  );
}
