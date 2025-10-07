declare module "react-markdown" {
  import type { ComponentType, ReactNode } from "react";
  const ReactMarkdown: ComponentType<{ children?: ReactNode } & Record<string, unknown>>;
  export default ReactMarkdown;
}


