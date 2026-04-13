export default function App() {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100vh',
      margin: 0,
      background: '#0a0a0c',
      color: '#e4e4e7',
      fontFamily: 'system-ui, -apple-system, sans-serif',
    }}>
      <div style={{
        width: 48,
        height: 48,
        border: '3px solid rgba(16, 185, 129, 0.2)',
        borderTop: '3px solid #10b981',
        borderRadius: '50%',
        animation: 'spin 1s linear infinite',
        marginBottom: 24,
      }} />
      <h2 style={{ fontSize: 20, fontWeight: 600, margin: '0 0 8px' }}>
        Building your project...
      </h2>
      <p style={{ fontSize: 14, color: '#71717a', margin: 0 }}>
        AI is writing code. This page will update automatically.
      </p>
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
