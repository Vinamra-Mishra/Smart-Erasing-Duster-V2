import type { Metadata } from 'next';
import '../index.css';
import { ClientWebSocketProvider } from '../components/ClientWebSocketProvider';
import { Navbar } from '../components/Navbar';

export const metadata: Metadata = {
  title: 'Smart Erasing Duster V2.1 — Digital Twin Mission Control',
  description: 'Dual-channel Digital Twin dashboard with RTP streaming and WebSocket telemetry',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 min-h-screen flex flex-col font-sans overflow-x-hidden select-none">
        <ClientWebSocketProvider>
          <Navbar />
          <main className="flex-1 flex flex-col min-h-0 w-full">
            {children}
          </main>
        </ClientWebSocketProvider>
      </body>
    </html>
  );
}
