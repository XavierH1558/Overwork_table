
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count > 1 else { exit(1) }
let url = URL(fileURLWithPath: args[1])
guard let image = NSImage(contentsOf: url), let cgImage = image.cgImage(forProposedRect: nil, separator: nil, context: nil) else { exit(1) }

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
let request = VNRecognizeTextRequest { req, err in
    guard let results = req.results as? [VNRecognizedTextObservation] else { return }
    for obs in results {
        if let top = obs.topCandidates(1).first {
            print(top.string)
        }
    }
}
request.recognitionLanguages = ["zh-Hant", "zh-Hans", "en-US"]
try? handler.perform([request])
