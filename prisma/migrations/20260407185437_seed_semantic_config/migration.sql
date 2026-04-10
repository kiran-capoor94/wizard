-- Seed initial semantic attribution threshold
INSERT INTO "SemanticConfig" (key, value, "updatedAt")
VALUES ('attribution_threshold', 0.75, NOW())
ON CONFLICT (key) DO NOTHING;
