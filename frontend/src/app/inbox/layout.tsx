export default function InboxLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="-m-4 md:-m-6 h-[calc(100vh-64px)] overflow-hidden">
      {children}
    </div>
  );
}
