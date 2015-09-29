CREATE TABLE IF NOT EXISTS "Schedules" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "Title" TEXT NOT NULL,
    "Interval" INTEGER NOT NULL DEFAULT (1),
    "SourceHost" TEXT NOT NULL,
    "DestinationHost" TEXT NOT NULL,
    "SourceDir" TEXT NOT NULL,
    "DestinationDir" TEXT NOT NULL,
    "Type" INTEGER NOT NULL
);
CREATE TABLE reports (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "Schedule" INTEGER NOT NULL,
    "date" INTEGER NOT NULL,
    "Result" INTEGER NOT NULL,
    "message" TEXT,
    "duration" INTEGER
);
