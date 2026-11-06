import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Toaster } from 'sonner'
import { ApiError } from '@/api/http'

function shouldRetry(count: number, e: unknown) {
  if (e instanceof ApiError && e.status >= 400 && e.status < 500) return false // never retry 4xx
  return count < 1
}

export function makeQueryClient() {
  return new QueryClient({
    queryCache: new QueryCache(),
    mutationCache: new MutationCache(),
    defaultOptions: { queries: { staleTime: 5_000, retry: shouldRetry, refetchOnWindowFocus: true }, mutations: { retry: false } },
  })
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(makeQueryClient)
  return (
    <QueryClientProvider client={client}>
      {children}
      <Toaster
        position="top-center"
        closeButton
        offset={{ top: 'max(env(safe-area-inset-top), 12px)' }}
        toastOptions={{
          classNames: {
            toast: '!rounded-panel !border !border-line !bg-bg !text-ink !shadow-pop !font-mono !text-[14px]',
            title: '!font-medium',
            description: '!text-muted',
            success: '!border-success/40',
            error: '!border-danger/40',
            warning: '!border-warning/50',
            actionButton: '!rounded-button !bg-inverse !text-on-inverse',
          },
        }}
      />
    </QueryClientProvider>
  )
}
