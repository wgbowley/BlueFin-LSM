#define DIR1_PIN 3
#define STEP1_PIN 4
#define EN1_PIN 2
#define STEPS_PER_REV 200   // MS17HD2P4200 (1.8° step)

#define EN2_PIN 10
#define STEP2_PIN 8
#define DIR2_PIN 9
#define STEPS_PER_MM 25     // D42HSA5041-23B

#define PI 3.141592653589793 

// ---------------- PARAMETERS ----------------
float fillFactor   = 0.7;      // slot fill efficiency
float length       = 4.0;      // mm slot length (slot opening in Z)
float height       = 4.0;      // mm slot height
float wireDiameter = 0.315;    // mm wire dia

// ---------------- STATE ----------------
long stepCount1 = 0;    // Motor 1 (rotation steps)
long stepCount2 = 0;    // Motor 2 (Z steps)

float totalTurns = 0;   // estimated turns for volume
float layerTurns = 0;   // turns per layer
float axialLength = 0;  // mm traverse length derived from turns

int currentLayer = 0;   // which layer we’re on
int totalLayers = 0;    // how many layers fit
bool zDirectionForward = true; // toggles every layer

// ---------------- FUNCTIONS ----------------
float zDisplacement(float rDisplacement, float axialLength, float layerTurns){
  return axialLength / (2 * PI * layerTurns) * rDisplacement;  
}

float estimateTurns(float length, float height, float wireDiameter, float fillFactor) {
    float slotArea = length * height;          // mm² slot area
    float wireArea = pow(wireDiameter, 2);     // square approx
    return (slotArea * fillFactor) / wireArea;
}

void setup() {
  pinMode(STEP1_PIN, OUTPUT);
  pinMode(DIR1_PIN, OUTPUT);
  pinMode(EN1_PIN, OUTPUT);

  pinMode(STEP2_PIN, OUTPUT);
  pinMode(DIR2_PIN, OUTPUT);
  pinMode(EN2_PIN, OUTPUT);

  digitalWrite(EN1_PIN, LOW); // enable drivers
  digitalWrite(EN2_PIN, LOW);

  digitalWrite(DIR1_PIN, HIGH); // bobbin rotate forward
  digitalWrite(DIR2_PIN, HIGH); // start Z forward

  // --- Estimate turns + layers ---
  totalTurns = estimateTurns(length, height, wireDiameter, fillFactor);
  totalLayers = floor(height / wireDiameter);         // how many layers in height
  layerTurns  = floor(totalTurns / totalLayers);      // turns per layer

  // Define axial travel from turns
  axialLength = 2 * PI * layerTurns;  // Z-axis displacement matches rotation span
}

void loop() {
  // Spin motor 1 one step
  digitalWrite(STEP1_PIN, HIGH);
  delayMicroseconds(500);
  digitalWrite(STEP1_PIN, LOW);
  delayMicroseconds(500);

  stepCount1++;

  // Angular displacement (per layer)
  float rDisplacement = (2 * PI) * (stepCount1 / (float)STEPS_PER_REV);

  // If one layer is finished
  if (rDisplacement >= 2 * PI * layerTurns) {
    currentLayer++;
    stepCount1 = 0;   // reset angle counter

    // Flip Z direction
    zDirectionForward = !zDirectionForward;
    digitalWrite(DIR2_PIN, zDirectionForward ? HIGH : LOW);

    // Stop after all layers
    if (currentLayer >= totalLayers) {
      while (1); // stop winding
    }
    return;
  }

  // Desired Z displacement in mm
  float zTarget = zDisplacement(rDisplacement, axialLength, layerTurns);

  // If we’re in backward mode → flip travel
  if (!zDirectionForward) {
    zTarget = axialLength - zTarget;
  }

  // Convert to steps
  long zStepsTarget = (long)(zTarget * STEPS_PER_MM);

  // Step Z motor if needed
  if (zStepsTarget > stepCount2) {
    digitalWrite(STEP2_PIN, HIGH);
    delayMicroseconds(500);
    digitalWrite(STEP2_PIN, LOW);
    delayMicroseconds(500);
    stepCount2++;
  }
}
