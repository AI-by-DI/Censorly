import { Play } from "lucide-react";
import { Button } from "../components/ui/button";
import Header from "../components/Header";
import CategoryRow from "../components/CategoryRow";
import { useNavigate } from "react-router-dom";
import { useCensorStore } from "../store/censorStore";

const Index = () => {
  const navigate = useNavigate();
  const { enabled } = useCensorStore(); // ✅ Sansür modu açık mı?

  const recommendedMovies = [
    { id: 1, title: "Midnight Protocol", image: "/movie-1.jpg", warnings: ["Violence", "Blood"] },
    { id: 2, title: "Shadow Realm", image: "/movie-2.jpg", warnings: ["Violence"] },
    { id: 3, title: "Quantum Edge", image: "/movie-3.jpg", warnings: ["Alcohol", "Violence"] },
    { id: 4, title: "Dark Echoes", image: "/movie-4.jpg", warnings: ["Blood", "Violence"] },
    { id: 5, title: "Night Shift", image: "/movie-1.jpg", warnings: ["Alcohol"] },
    { id: 6, title: "Silent Fear", image: "/movie-2.jpg", warnings: ["Violence", "Spider"] },
  ];

  const trendingMovies = [
    { id: 7, title: "Urban Legends", image: "/movie-3.jpg", warnings: ["Clown"] },
    { id: 8, title: "Desert Storm", image: "/movie-4.jpg", warnings: ["Violence", "Snake"] },
    { id: 9, title: "City Lights", image: "/movie-1.jpg", warnings: ["Alcohol"] },
    { id: 10, title: "Ocean Deep", image: "/movie-2.jpg", warnings: [] },
    { id: 11, title: "Mountain High", image: "/movie-3.jpg", warnings: ["Violence"] },
    { id: 12, title: "River Run", image: "/movie-4.jpg", warnings: ["Blood"] },
  ];

  // ✅ Sansür durumu aktifse player'a filtreli olarak yönlendir
  const handleWatch = () => {
    if (enabled) {
      navigate("/player/1?mode=censored");
    } else {
      navigate("/player/1?mode=original");
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />

      {/* Hero Section */}
      <section className="relative h-[90vh] mb-8">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: "url('/hero-banner.jpg')" }}
        />
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/60 to-transparent" />

        <div className="relative container mx-auto h-full flex items-center px-8">
          <div className="max-w-2xl space-y-6 animate-fade-in">
            <h1 className="text-6xl font-bold leading-tight">The Reckoning</h1>
            <p className="text-xl text-muted-foreground">
              When darkness falls, only the brave survive. A gripping thriller that will keep you on
              the edge of your seat. Watch with personalized content filtering.
            </p>

            {/* 🔘 Tek buton, davranışı switch'e göre değişiyor */}
            <div className="flex gap-4">
              <Button
                size="lg"
                onClick={handleWatch}
                className={`${
                  enabled
                    ? "bg-secondary text-secondary-foreground hover:bg-secondary/80"
                    : "bg-primary hover:bg-primary/90"
                }`}
              >
                <Play className="w-5 h-5 mr-2" />
                {enabled ? "Watch with Filters" : "Watch Now"}
              </Button>
            </div>

            <div className="flex gap-2 flex-wrap">
              <span className="px-3 py-1 rounded-full text-sm bg-violence/20 text-violence border border-violence/30">
                Contains Violence
              </span>
              <span className="px-3 py-1 rounded-full text-sm bg-blood/20 text-blood border border-blood/30">
                Contains Blood
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* Content Rows */}
      <div className="pb-16">
        <CategoryRow title="Recommended for You" movies={recommendedMovies} />
        <CategoryRow title="Trending Now" movies={trendingMovies} />
        <CategoryRow title="Newly Added" movies={recommendedMovies} />
      </div>
    </div>
  );
};

export default Index;
