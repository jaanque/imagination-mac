import SwiftUI

struct ContentView: View {
    @State private var counter = 0

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "cloud.fill")
                .font(.system(size: 56))
                .foregroundStyle(.blue)

            Text("Cloud Swift Builder")
                .font(.title.bold())

            Text("Compiled in the cloud without a local Mac.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Text("Taps: \(counter)")
                .font(.title2.monospacedDigit())
                .padding(.top, 8)

            Button("Increment Counter") {
                counter += 1
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(32)
    }
}

#Preview {
    ContentView()
}
