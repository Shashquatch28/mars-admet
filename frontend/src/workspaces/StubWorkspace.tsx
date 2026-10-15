// Placeholder for the workspaces beyond Predict. The shell, row grammar,
// reliability language and provenance readout are identical across all four — only
// Predict is built in this pass. Switching here is instant (zero animation), which
// is the point this placeholder also demonstrates.
export function StubWorkspace({ name }: { name: string }) {
  return (
    <section
      aria-label={name}
      style={{
        flex: 1,
        minWidth: 0,
        display: "grid",
        placeItems: "center",
        textAlign: "center",
        background: "var(--surface-void)",
        padding: "24px",
      }}
    >
      <div style={{ maxWidth: "34ch" }}>
        <div
          style={{
            fontFamily: "var(--cond)",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            fontSize: 11,
            color: "var(--text-secondary)",
            marginBottom: 8,
          }}
        >
          {name}
        </div>
        <p style={{ margin: 0, fontSize: 11, color: "var(--text-quiet)", lineHeight: 1.6 }}>
          This workspace isn&rsquo;t part of this pass. It inherits the same shell, endpoint row grammar,
          reliability language and provenance readout as Predict.
        </p>
      </div>
    </section>
  );
}
