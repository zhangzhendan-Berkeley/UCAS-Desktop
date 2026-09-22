import Foundation
import EventKit

let store = EKEventStore()
let semaphore = DispatchSemaphore(value: 0)
var granted = false
if #available(macOS 14.0, *) {
    store.requestFullAccessToEvents { allowed, _ in granted = allowed; semaphore.signal() }
} else {
    store.requestAccess(to: .event) { allowed, _ in granted = allowed; semaphore.signal() }
}
while semaphore.wait(timeout: .now()) != .success {
    RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.1))
}
guard granted else { fputs("Calendar access denied\n", stderr); exit(1) }
let calendars = store.calendars(for: .event)
if CommandLine.arguments.contains("--list") {
    let rows = calendars.map { ["title": $0.title, "id": $0.calendarIdentifier,
        "source": $0.source.title, "sourceType": String($0.source.sourceType.rawValue),
        "writable": String($0.allowsContentModifications)] }
    print(String(data: try JSONSerialization.data(withJSONObject: rows), encoding: .utf8)!)
    exit(0)
}
let matches = calendars.filter { $0.title == "UCAS" && $0.source.title == "iCloud" && $0.source.sourceType == .calDAV && $0.allowsContentModifications }
guard matches.count == 1 else { fputs("A unique writable iCloud/UCAS calendar was not found\n", stderr); exit(1) }
let calendar = matches[0]
struct Entry: Decodable { let start: Double; let end: Double; let title: String; let location: String }
let entries = try JSONDecoder().decode([Entry].self, from: FileHandle.standardInput.readDataToEndOfFile())
var added = 0
var updated = 0
for item in entries {
    let start = Date(timeIntervalSince1970: item.start)
    let end = Date(timeIntervalSince1970: item.end)
    guard end > start else { continue }
    let predicate = store.predicateForEvents(withStart: start, end: end, calendars: [calendar])
    let existing = store.events(matching: predicate).filter { $0.title == item.title && abs($0.startDate.timeIntervalSince(start)) < 1 }
    if !existing.isEmpty {
        for event in existing where !item.location.isEmpty && event.location != item.location {
            event.location = item.location
            try store.save(event, span: .thisEvent, commit: false)
            updated += 1
        }
        continue
    }
    let event = EKEvent(eventStore: store)
    event.calendar = calendar
    event.title = item.title
    event.startDate = start
    event.endDate = end
    event.location = item.location
    event.notes = "UCAS Desktop 自动同步"
    try store.save(event, span: .thisEvent, commit: false)
    added += 1
}
try store.commit()
print("iCloud/UCAS: added \(added), updated \(updated), processed \(entries.count)")
