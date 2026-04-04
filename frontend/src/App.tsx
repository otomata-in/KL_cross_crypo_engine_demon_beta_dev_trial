import { useArbitrageSocket } from './hooks/useArbitrageSocket';
import { useArbitrageStore } from './store';
import { HeaderHUD } from './components/HeaderHUD';
import { TokenGrid } from './components/TokenGrid';
import { ActionFeed } from './components/ActionFeed';
import { WaitingScreen } from './components/WaitingScreen';

function App() {
  // Establish WebSocket connection on mount
  useArbitrageSocket();

  const liveState = useArbitrageStore((s) => s.liveState);
  const wsStatus = useArbitrageStore((s) => s.wsStatus);

  // Show waiting screen if not connected or no data yet
  if (!liveState || (wsStatus !== 'connected' && wsStatus !== 'connecting')) {
    return <WaitingScreen />;
  }

  // Show waiting screen while connecting and no data
  if (!liveState && wsStatus === 'connecting') {
    return <WaitingScreen />;
  }

  return (
    <div className="min-h-screen bg-surface">
      <HeaderHUD />

      <div className="flex h-[calc(100vh-88px)]">
        {/* Main content — Token Grid */}
        <main className="flex-1 overflow-y-auto p-4">
          <TokenGrid />
        </main>

        {/* Sidebar — Action Feed */}
        <aside className="w-80 xl:w-96 border-l border-border bg-card/30 flex flex-col">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-300">📡 Live Feed</h2>
            <span className="text-[10px] text-gray-600 font-mono">
              {liveState.opp_total} total
            </span>
          </div>
          <div className="flex-1 overflow-hidden p-2">
            <ActionFeed />
          </div>
        </aside>
      </div>
    </div>
  );
}

export default App;
