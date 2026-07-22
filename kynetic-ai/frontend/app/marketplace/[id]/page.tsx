import type { Metadata } from "next";
import ListingDetailPage from "./ListingDetailPage";

export const metadata: Metadata = {
  title: "Listing Detail",
  description: "Full compute listing specs, benchmarks, and rental pricing.",
};

export default function Page({ params }: { params: { id: string } }) {
  return <ListingDetailPage id={params.id} />;
}
