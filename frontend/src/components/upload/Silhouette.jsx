/** Translucent alignment guide, shaped to match whichever region is being
 * captured (`pose`: front | hairline | left | right | crown | back). Shown
 * both as a pre-capture placeholder and layered live on top of the camera
 * feed during capture, so the user lines up the same way every session --
 * consistent framing makes the baseline/current change-map alignment far
 * more reliable. */

function FrontFace({ emphasizeHairline }) {
  return (
    <>
      <path d="M100,26 C132,26 150,56 150,96 C150,142 126,176 100,176 C74,176 50,142 50,96 C50,56 68,26 100,26 Z"
        fill="none" stroke="white" strokeWidth="2" strokeDasharray="6 6" />
      <path d="M64,56 Q100,34 136,56" fill="none" stroke="white"
        strokeWidth={emphasizeHairline ? 3 : 1.5} strokeDasharray={emphasizeHairline ? undefined : "4 4"} />
      <g opacity={emphasizeHairline ? 0.35 : 1}>
        <path d="M70,96 Q80,89 90,96" fill="none" stroke="white" strokeWidth="1.5" />
        <path d="M110,96 Q120,89 130,96" fill="none" stroke="white" strokeWidth="1.5" />
        <ellipse cx="80" cy="102" rx="5" ry="3" fill="none" stroke="white" strokeWidth="1.5" />
        <ellipse cx="120" cy="102" rx="5" ry="3" fill="none" stroke="white" strokeWidth="1.5" />
        <path d="M100,106 L94,128 Q100,133 106,128" fill="none" stroke="white" strokeWidth="1.5" />
        <path d="M84,146 Q100,156 116,146" fill="none" stroke="white" strokeWidth="1.5" />
      </g>
    </>
  );
}

// Authored facing left (turned toward screen-left); the "right" pose reuses
// this mirrored via a transform rather than duplicating the paths.
function LeftProfile() {
  return (
    <>
      <ellipse cx="115" cy="96" rx="38" ry="72" fill="none" stroke="white" strokeWidth="2" strokeDasharray="6 6" transform="rotate(-8 115 96)" />
      <path d="M84,58 Q115,40 146,58" fill="none" stroke="white" strokeWidth="1.5" strokeDasharray="4 4" />
      <path d="M84,88 Q76,96 84,106" fill="none" stroke="white" strokeWidth="1.5" />
      <path d="M118,80 Q128,74 138,80" fill="none" stroke="white" strokeWidth="1.5" />
      <ellipse cx="128" cy="88" rx="5" ry="3" fill="none" stroke="white" strokeWidth="1.5" />
      <path d="M140,90 Q150,100 140,112" fill="none" stroke="white" strokeWidth="1.5" />
      <path d="M120,128 Q132,134 142,126" fill="none" stroke="white" strokeWidth="1.5" />
    </>
  );
}

function CrownGuide() {
  return (
    <>
      <circle cx="100" cy="100" r="65" fill="none" stroke="white" strokeWidth="2" strokeDasharray="6 6" />
      <path d="M100,88 a12,12 0 1,1 -8,20" fill="none" stroke="white" strokeWidth="1.5" />
      <line x1="33" y1="100" x2="45" y2="100" stroke="white" strokeWidth="1.5" />
      <line x1="155" y1="100" x2="167" y2="100" stroke="white" strokeWidth="1.5" />
    </>
  );
}

function BackGuide() {
  return (
    <g opacity="0.6">
      <ellipse cx="100" cy="98" rx="52" ry="68" fill="none" stroke="white" strokeWidth="2" strokeDasharray="3 7" />
      <circle cx="100" cy="90" r="3" fill="white" />
    </g>
  );
}

export default function Silhouette({ pose = "front" }) {
  return (
    <svg viewBox="0 0 200 200" className="absolute inset-0 w-full h-full opacity-50 pointer-events-none" aria-hidden="true">
      {pose === "left" && <LeftProfile />}
      {pose === "right" && <g transform="translate(200,0) scale(-1,1)"><LeftProfile /></g>}
      {pose === "crown" && <CrownGuide />}
      {pose === "back" && <BackGuide />}
      {pose !== "left" && pose !== "right" && pose !== "crown" && pose !== "back" && (
        <FrontFace emphasizeHairline={pose === "hairline"} />
      )}
    </svg>
  );
}
