import type { ReactElement, ReactNode } from "react";
import {
  render,
  renderHook as rtlRenderHook,
  type RenderOptions,
  type RenderHookOptions,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

interface WrapperProps {
  children: ReactNode;
}

function AllProviders({ children }: WrapperProps) {
  const queryClient = createTestQueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

function customRender(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper">,
) {
  return render(ui, { wrapper: AllProviders, ...options });
}

function customRenderHook<Result, Props>(
  hook: (props: Props) => Result,
  options?: Omit<RenderHookOptions<Props>, "wrapper">,
) {
  return rtlRenderHook(hook, { wrapper: AllProviders, ...options });
}

// Re-export everything from RTL
export * from "@testing-library/react";
export { default as userEvent } from "@testing-library/user-event";
// Override render and renderHook
export {
  customRender as render,
  customRenderHook as renderHook,
  createTestQueryClient,
};
