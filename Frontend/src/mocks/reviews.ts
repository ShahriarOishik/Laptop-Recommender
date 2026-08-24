/**
 * Short canned "review" snippets keyed by category, standing in for the
 * unstructured review text the real Spark/FAISS pipeline would index and retrieve.
 */
export const CATEGORY_REVIEW_SNIPPETS: Record<string, string> = {
  Gaming:
    "Handles modern AAA titles at high settings with stable frame rates; thermals stay reasonable under sustained load.",
  Programming:
    "Compiles large projects quickly and multitasks well across editors, containers, and browser tabs without slowing down.",
  "Machine Learning":
    "Local model experimentation and fine-tuning feel smooth thanks to the GPU and memory headroom; handles moderate batch sizes.",
  Student:
    "Light enough to carry between classes all day, with battery life that comfortably covers a full lecture schedule.",
  Office:
    "Great for spreadsheets, video calls, and document editing; fans stay quiet during typical office workloads.",
  Business:
    "Durable build quality and a comfortable keyboard make it well suited to travel-heavy business use.",
  "Graphic Design":
    "Color-accurate display makes it dependable for design work that needs consistent, accurate colors.",
  "Video Editing":
    "Handles 4K timelines and export jobs without excessive slowdown, aided by strong GPU-accelerated encoding.",
  "Content Creation":
    "Balances solid creative-app performance with a display sharp enough for detailed content review work.",
  "General Use":
    "A dependable everyday machine for browsing, streaming, and typical home use without any major complaints.",
  Portable:
    "Noticeably easy to carry, sliding easily into a daily bag without adding much noticeable weight.",
};
