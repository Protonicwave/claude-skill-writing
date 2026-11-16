methods notes (glitch classifier)

- data: Gravity Spy, 22 glitch classes, Q-transform images 140x170 px, 4 time windows stacked
- split 70/15/15, stratified by class, seed 42
- model: ResNet-18 pretrained on ImageNet, last layer replaced, 22 outputs
- trained 30 epochs, Adam, lr 1e-4, batch 64, early stopping on val loss (patience 5)
- PyTorch 2.3.1, torchvision 0.18.1, scikit-learn (for the split), numpy
- class weights = inverse frequency
- accuracy uncertainty: bootstrap over the test set, 1000 resamples
- result: 94.1% test accuracy +/- 0.3%
- ran on one A100 on the department cluster, about 2 h
