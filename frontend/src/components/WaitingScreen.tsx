import React from 'react';
import { useArbitrageStore } from '../store';
import { Loader2, WifiOff, ServerOff } from 'lucide-react';

export const WaitingScreen: React.FC = () => {
  const wsStatus = useArbitrageStore((s) => s.wsStatus);

  const isConnecting = wsStatus === 'connecting';
  const isDisconnected = wsStatus === 'disconnected' || wsStatus === 'error';

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center">
      <div className="text-center space-y-6 max-w-md mx-auto px-4">
        {/* Animated icon */}
        <div className="relative mx-auto w-20 h-20">
          <div className={`absolute inset-0 rounded-full border-2 ${
            isConnecting ? 'border-accent/30 animate-ping' : 'border-red-500/20'
          }`} />
          <div className={`absolute inset-2 rounded-full border-2 ${
            isConnecting ? 'border-accent/50 animate-pulse' : 'border-red-500/30'
          }`} />
          <div className="absolute inset-0 flex items-center justify-center">
            {isConnecting ? (
              <Loader2 className="w-8 h-8 text-accent-light animate-spin" />
            ) : isDisconnected ? (
              <WifiOff className="w-8 h-8 text-red-400" />
            ) : (
              <ServerOff className="w-8 h-8 text-gray-500" />
            )}
          </div>
        </div>

        {/* Text */}
        <div>
          <h2 className="text-xl font-bold text-gray-200 mb-2">
            {isConnecting ? 'Connecting to Backend...' : 'Backend Disconnected'}
          </h2>
          <p className="text-sm text-gray-500">
            {isConnecting
              ? 'Establishing WebSocket connection to backend...'
              : 'Unable to reach the Python backend. Make sure the server is running and accessible.'}
          </p>
        </div>

        {/* Connection status */}
        <div className="flex items-center justify-center gap-2 text-xs text-gray-600 font-mono">
          <span className={`w-2 h-2 rounded-full ${
            isConnecting ? 'bg-yellow-500 animate-pulse' : 'bg-red-500'
          }`} />
          <span>Backend</span>
          <span>•</span>
          <span>{wsStatus}</span>
        </div>

        {isDisconnected && (
          <div className="bg-card border border-border rounded-lg p-4 text-left text-xs text-gray-500 font-mono">
            <p className="text-gray-400 mb-2">Start the backend with:</p>
            <code className="text-accent-light">source venv/bin/activate && python ws_server.py</code>
          </div>
        )}
      </div>
    </div>
  );
};
